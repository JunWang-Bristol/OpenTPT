"""TPT sweep over (frequency, B_peak) grid with explicit clipping and
saturation guards.

For every (f, B_target) cell:
  1) Start at a SAFE low V (0.3 V regardless of estimate).
  2) Probe burst, narrow scope ranges, re-capture, measure B_actual and PSU
     current draw.
  3) If PSU current > I_PSU_LIMIT, abort cell (the supply is current-limiting
     -- audible 'beep' on hardware).
  4) Otherwise scale V toward target (capped to 2x step), re-probe.
  5) Once converged, run volt-second balance and compute Q, P_core.
  6) Plot losses vs f (one curve per B level), and write CSV.
"""
import os, sys, time
sys.path.insert(0, 'src')

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from tpt import CoreLossMeasurement, theoretical_inductance, CORE_DATABASE


# ---------- configuration ----------
CORE       = "T26"
MATERIAL   = "3C90"
N1         = 10
N2         = 1
N_HALF     = 8
SAMPLES    = 2500
CH_PWM     = 2

# Sweep grid
FREQS      = [50e3, 100e3, 200e3, 500e3, 1e6]
B_TARGETS  = [0.025, 0.050, 0.100, 0.150]

# Safety
V_START      = 0.3    # always begin each cell here regardless of estimate
V_MAX        = 25.0
B_SAT_LIMIT  = 0.250  # treat as saturation; abort cell
B_TOL        = 0.10
V_CAL_ITERS  = 6
V_STEP_MAX   = 2.5    # cap ramp factor per iter
I_PSU_LIMIT  = 0.30   # >300 mA average from a single PSU channel = current-limit / beep
BAL_TOL      = 0.05
BAL_MAX_ITER = 5

# Per-channel range candidates (in scope volts post-probe-scale)
# PicoScope2408B supports 20mV-20V; including the narrow ranges drastically
# reduces 8-bit-ADC quantization noise on B integration at low V_sec.
V_RANGES = [0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]
I_RANGES = [0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
B_REJECT_TOL = 0.20    # reject cell if final B_peak is >20% off target


def trapz(y, x):
    """numpy compatibility shim — np.trapezoid is numpy>=2."""
    return np.trapz(y, x)


def find_pwm_edges(pwm, vthresh=1.0):
    above = pwm > vthresh
    rising  = np.where((~above[:-1]) &  above[1:])[0] + 1
    falling = np.where( above[:-1] & (~above[1:]))[0] + 1
    return rising, falling


def apply_labels(meas):
    s = meas.scope
    s.set_channel_label(meas.CH_VOLTAGE,   'V_pri')
    s.set_channel_label(meas.CH_SECONDARY, 'V_sec')
    s.set_channel_label(CH_PWM,            'PWM')
    s.set_channel_label(meas.CH_CURRENT,   'I')


def fire_and_capture(meas, pulses_s):
    s = meas.scope
    apply_labels(meas)
    meas.board.clear_pulses()
    for T in pulses_s:
        meas.board.add_pulse(T)
    s.set_rising_trigger(CH_PWM, 0.5, timeout=0)
    s.start_single_acquisition()
    time.sleep(0.4)
    meas.board.run_pulses(1)
    deadline = time.monotonic() + 5
    while True:
        if s.get_acquisition_state() == 'COMP': break
        if time.monotonic() > deadline:
            return None
        time.sleep(0.05)
    return s.read_data([meas.CH_VOLTAGE, meas.CH_SECONDARY, CH_PWM, meas.CH_CURRENT])


def psu_currents(meas):
    """Return (I_ch1, I_ch2) in amps, or (nan, nan) if read fails."""
    try:
        return meas.psu.get_measured_current(1), meas.psu.get_measured_current(2)
    except Exception:
        return float('nan'), float('nan')


def pick_smallest_range(peak_real, candidates, probe_scale, headroom=1.4):
    needed = peak_real * headroom
    for r in candidates:
        if r * probe_scale >= needed:
            return r
    return candidates[-1]


def configure_ranges(meas, rv, rsv, ri):
    s = meas.scope
    s.set_channel_configuration(meas.CH_VOLTAGE,   rv,  'DC', 0.0)
    s.set_channel_configuration(meas.CH_SECONDARY, rsv, 'DC', 0.0)
    s.set_channel_configuration(CH_PWM,            5.0, 'DC', 0.0)
    s.set_channel_configuration(meas.CH_CURRENT,   ri,  'DC', 0.0)
    apply_labels(meas)


def probe_at_voltage(meas, V, pulses_s, sample_dt):
    """Set V, fire one probe burst at coarse range to measure peaks, then
    re-fire at narrow range. Returns (df_narrow, peaks_dict, psu_I).
    """
    meas.psu.set_source_voltage(meas.PSU_CHANNEL,     V)
    meas.psu.set_source_voltage(meas.PSU_CHANNEL_NEG, V)
    time.sleep(0.25)

    s = meas.scope
    s.set_sampling_time(sample_dt)
    # Coarse probe
    configure_ranges(meas, V_RANGES[-1], V_RANGES[-1], I_RANGES[-1])
    df = fire_and_capture(meas, pulses_s)
    if df is None:
        return None, None, None
    vp_peak = float(np.abs(df['V_pri']).max())
    vs_peak = float(np.abs(df['V_sec']).max())
    i_peak  = float(np.abs(df['I']).max())
    # Narrow ranges
    rv  = pick_smallest_range(vp_peak, V_RANGES, meas.input_voltage_probe_scale)
    rsv = pick_smallest_range(vs_peak, V_RANGES, meas.output_voltage_probe_scale)
    ri  = pick_smallest_range(i_peak,  I_RANGES, meas.current_probe_scale)
    configure_ranges(meas, rv, rsv, ri)
    # Re-fire at narrow ranges (this is what we use for B measurement)
    df2 = fire_and_capture(meas, pulses_s)
    if df2 is None:
        return None, None, None
    # PSU current after burst
    Ich1, Ich2 = psu_currents(meas)
    peaks = dict(vp=vp_peak, vs=vs_peak, i=i_peak, rv=rv, rsv=rsv, ri=ri)
    return df2, peaks, (Ich1, Ich2)


def get_target_cycle(df):
    pwm = df['PWM'].to_numpy()
    rising, falling = find_pwm_edges(pwm, vthresh=1.0)
    if len(rising) < 2: return None, None
    i_start = int(rising[-2])
    falls_after = falling[falling > i_start]
    if not len(falls_after): return None, None
    i_mid = int(falls_after[0])
    rises_after = rising[rising > i_mid]
    i_end = int(rises_after[0]) if len(rises_after) else len(pwm) - 1
    return i_start, i_end


def measure_B_peak(df, Ae, i_start, i_end):
    vs = df['V_sec'].to_numpy()
    t  = df['time'].to_numpy()
    dt = t[1] - t[0]
    B = np.cumsum(vs * dt) / (N2 * Ae)
    p = np.polyfit(t[i_start:i_end+1], B[i_start:i_end+1], 1)
    B = B - np.polyval(p, t)
    B_c = B[i_start:i_end]
    return (B_c.max() - B_c.min()) / 2.0, B


def calibrate_voltage(meas, pulses_s, B_target, Ae, sample_dt):
    """Iteratively scale V (start at V_START, cap step factor) until B ~ target."""
    V = V_START
    last_dfs = []
    for it in range(V_CAL_ITERS):
        if V > V_MAX: V = V_MAX
        df, peaks, psu_I = probe_at_voltage(meas, V, pulses_s, sample_dt)
        if df is None:
            print(f'  [cal] iter {it+1}: capture failed'); return None, None, None
        if any(abs(I) > I_PSU_LIMIT for I in psu_I if I == I):  # NaN check
            print(f'  [cal] iter {it+1}: PSU current {psu_I[0]*1e3:.0f}/{psu_I[1]*1e3:.0f}mA '
                  f'> {I_PSU_LIMIT*1e3:.0f}mA - BEEP/CL, abort cell')
            return None, None, None
        i_s, i_e = get_target_cycle(df)
        if i_s is None:
            print(f'  [cal] iter {it+1}: no PWM cycle visible'); return None, None, None
        B_peak, _ = measure_B_peak(df, Ae, i_s, i_e)
        rel_err = abs(B_peak - B_target) / B_target
        print(f'  [cal] iter {it+1}: V={V:.3f}V  B_peak={B_peak*1e3:.1f}mT  '
              f'(target {B_target*1e3:.0f}mT, err {rel_err*100:.0f}%)  '
              f'PSU I={psu_I[0]*1e3:.0f}/{psu_I[1]*1e3:.0f}mA')
        # Saturation guard
        if B_peak > B_SAT_LIMIT:
            print(f'  [cal] B_peak > SAT - abort'); return None, None, None
        if rel_err < B_TOL:
            return V, df, (i_s, i_e)
        if B_peak < 1e-4:
            V_new = V * V_STEP_MAX  # B essentially zero, ramp aggressively
        else:
            scale = B_target / B_peak
            scale = max(1.0/V_STEP_MAX, min(V_STEP_MAX, scale))
            V_new = V * scale
        V_new = max(0.05, min(V_MAX, V_new))
        # Stuck-at-max detection: if we already maxed out and B isn't growing toward target
        if V >= V_MAX - 1e-3 and B_peak < B_target * 0.5:
            print(f'  [cal] V at max ({V_MAX}V) but B<{B_target*1e3*0.5:.0f}mT -> unreachable, abort')
            return None, None, None
        V = V_new
    print(f'  [cal] did not converge after {V_CAL_ITERS} iterations')
    # use last result anyway if reasonable
    if rel_err < 0.30:
        return V, df, (i_s, i_e)
    return None, None, None


def _measure_balance_state(meas, pulses_s, V_pos, V_neg, Ae):
    """Set PSU, fire one burst, return (df, i_s, i_e, residual_vs, B_peak,
    delta_I, I_pp, psu_I) or (None,...) on failure."""
    meas.psu.set_source_voltage(meas.PSU_CHANNEL_NEG, V_neg)
    meas.psu.set_source_voltage(meas.PSU_CHANNEL,     V_pos)
    time.sleep(0.15)
    df = fire_and_capture(meas, pulses_s)
    if df is None: return None
    psu_I = psu_currents(meas)
    if any(abs(I) > I_PSU_LIMIT for I in psu_I if I == I):
        return ('PSU_LIMIT', psu_I)
    i_s, i_e = get_target_cycle(df)
    if i_s is None: return ('NO_CYCLE', df)
    t  = df['time'].to_numpy()
    vs = df['V_sec'].to_numpy()
    I  = df['I'].to_numpy()
    sl = slice(i_s, i_e + 1)
    residual_vs = float(trapz(vs[sl], t[sl]))
    dt = t[1] - t[0]
    B_int = np.cumsum(vs * dt) / (N2 * Ae)
    p = np.polyfit(t[sl], B_int[sl], 1)
    B_int = B_int - np.polyval(p, t)
    B_c = B_int[i_s:i_e]
    B_peak = (B_c.max() - B_c.min()) / 2.0
    delta_I = float(I[i_e] - I[i_s])
    I_pp = max(I[i_s:i_e].max() - I[i_s:i_e].min(), 1e-6)
    return dict(df=df, i_s=i_s, i_e=i_e,
                residual_vs=residual_vs, B_peak=B_peak,
                delta_I=delta_I, I_pp=I_pp, psu_I=psu_I)


def balance_voltages(meas, pulses_s, V_init, sample_dt, B_target, Ae):
    """Two-phase balance — clean separation of concerns.

    Phase A (drift): with V_pos held, adjust V_neg by residual_vs/T_half
                     to drive ∫V_sec dt → 0. Stops when |residual_vs| is
                     at the noise floor.
    Phase B (amplitude): scale BOTH V_pos and V_neg by the same factor
                     (B_target/B_peak). Same scale on both sides preserves
                     the volt-second balance achieved in phase A.
    Final verify: one extra burst to read final state.
    """
    V_pos = V_init; V_neg = V_init
    DV_NEG_MAX = 0.4
    PHASE_A_ITERS = 2          # noise-limited: more iters chase noise
    RES_NOISE_FLOOR = 0.15e-6  # V·s — below this, residual is measurement noise
    SCALE_LO, SCALE_HI = 0.5, 2.5
    OUTER_ITERS = 2            # repeat A→B if Phase B scale was clipped

    # NOTE: empirically, V_sec polarity on this hardware is opposite to V_pri:
    # positive residual_vs corresponds to V_neg too HIGH (not too low). The
    # correction is therefore V_neg -= residual/T_half, not +=.
    last_state = None
    for outer in range(OUTER_ITERS):
        best_V_neg = V_neg
        best_abs_res = float('inf')
        # ---- Phase A: volt-second balance ----
        for it in range(PHASE_A_ITERS):
            st = _measure_balance_state(meas, pulses_s, V_pos, V_neg, Ae)
            if st is None: return V_pos, V_neg, None, None, None
            if isinstance(st, tuple) and st[0] == 'PSU_LIMIT':
                print(f'  [bal-A] o{outer+1} iter {it+1}: PSU current limit '
                      f'{st[1][0]*1e3:.0f}/{st[1][1]*1e3:.0f}mA -> abort')
                return V_pos, V_neg, None, None, None
            if isinstance(st, tuple) and st[0] == 'NO_CYCLE':
                return V_pos, V_neg, st[1], None, None
            rel_drift = abs(st['delta_I']) / st['I_pp']
            print(f'  [bal-A] o{outer+1} iter {it+1}: V+/-={V_pos:.3f}/{V_neg:.3f}  '
                  f'intVs={st["residual_vs"]*1e6:+.2f}uVs  dI={st["delta_I"]*1e3:+.1f}mA(rel {rel_drift*100:.0f}%)  '
                  f'B={st["B_peak"]*1e3:.1f}mT  PSU={st["psu_I"][0]*1e3:.0f}/{st["psu_I"][1]*1e3:.0f}mA')
            if abs(st['residual_vs']) < best_abs_res:
                best_abs_res = abs(st['residual_vs']); best_V_neg = V_neg; last_state = st
            if abs(st['residual_vs']) < RES_NOISE_FLOOR:
                break
            T_cycle = st['df']['time'].to_numpy()[st['i_e']] - st['df']['time'].to_numpy()[st['i_s']]
            T_half_neg = T_cycle / 2.0
            # Sign convention: V_sec polarity is flipped relative to V_pri here, so SUBTRACT.
            dV_neg = -st['residual_vs'] / T_half_neg
            dV_neg = max(-DV_NEG_MAX, min(DV_NEG_MAX, dV_neg))
            V_neg = max(0.1, min(V_MAX, V_neg + dV_neg))

        # Revert to best V_neg seen during Phase A (in case a later iter overshot)
        V_neg = best_V_neg

        # ---- Phase B: scale to hit B_target (preserves V_pos/V_neg ratio) ----
        scale_clipped = False
        if last_state and last_state['B_peak'] > 1e-4:
            scale_raw = B_target / last_state['B_peak']
            scale = max(SCALE_LO, min(SCALE_HI, scale_raw))
            scale_clipped = abs(scale_raw - scale) > 1e-3
            if abs(scale - 1.0) > 0.02:
                V_pos = max(0.1, min(V_MAX, V_pos * scale))
                V_neg = max(0.1, min(V_MAX, V_neg * scale))
                print(f'  [bal-B] o{outer+1} scale x{scale:.3f} (raw {scale_raw:.2f}'
                      f'{", CLIP" if scale_clipped else ""}): '
                      f'V+/-={V_pos:.3f}/{V_neg:.3f}  (B was {last_state["B_peak"]*1e3:.1f}mT)')
        # If Phase B converged within scale tol, no need for another outer pass
        if last_state and last_state['B_peak'] > 1e-4 and not scale_clipped \
                and abs(B_target / last_state['B_peak'] - 1.0) < B_TOL:
            break

    # ---- Final verify ----
    st = _measure_balance_state(meas, pulses_s, V_pos, V_neg, Ae)
    if st is None: return V_pos, V_neg, None, None, None
    if isinstance(st, tuple) and st[0] == 'PSU_LIMIT':
        print(f'  [bal-V] PSU current limit -> abort')
        return V_pos, V_neg, None, None, None
    if isinstance(st, tuple) and st[0] == 'NO_CYCLE':
        return V_pos, V_neg, st[1], None, None
    rel_drift = abs(st['delta_I']) / st['I_pp']
    rel_B_err = abs(st['B_peak'] - B_target) / B_target
    print(f'  [bal-V] V+/-={V_pos:.3f}/{V_neg:.3f}  '
          f'intVs={st["residual_vs"]*1e6:+.2f}uVs  dI={st["delta_I"]*1e3:+.1f}mA(rel {rel_drift*100:.0f}%)  '
          f'B={st["B_peak"]*1e3:.1f}mT(err {rel_B_err*100:.0f}%)')
    return V_pos, V_neg, st['df'], st['i_s'], st['i_e']


def virtual_close(B, t, i_s, i_e):
    out = B.copy()
    drift = (B[i_e] - B[i_s]) / (t[i_e] - t[i_s])
    out[i_s:i_e+1] = B[i_s:i_e+1] - drift * (t[i_s:i_e+1] - t[i_s])
    return out


def measure_cell(meas, f, B_target, Ae, le, L_henry):
    T_half = 1.0 / (2.0 * f)
    pulses_s = [T_half] * N_HALF
    burst_s = T_half * N_HALF
    sample_dt = max(20e-9, burst_s * 1.5 / SAMPLES)
    for x in [20e-9, 50e-9, 100e-9, 200e-9, 500e-9, 1e-6, 2e-6]:
        if x >= sample_dt:
            sample_dt = x; break
    print(f'\n=== f={f/1e3:.0f}kHz  B={B_target*1e3:.0f}mT  (dt={sample_dt*1e9:.0f}ns) ===')

    # 1) Calibrate V to hit B_target (start safe)
    V_cal, df_cal, cycle = calibrate_voltage(meas, pulses_s, B_target, Ae, sample_dt)
    if V_cal is None:
        # safety: drop voltage to something low before next cell
        meas.psu.set_source_voltage(meas.PSU_CHANNEL,     V_START)
        meas.psu.set_source_voltage(meas.PSU_CHANNEL_NEG, V_START)
        return None

    # 2) Volt-second balance (also re-tunes V_pos to keep B at target)
    print('  [bal] balancing volt-seconds')
    V_pos, V_neg, df, i_s, i_e = balance_voltages(meas, pulses_s, V_cal, sample_dt, B_target, Ae)
    if df is None or i_s is None:
        meas.psu.set_source_voltage(meas.PSU_CHANNEL,     V_START)
        meas.psu.set_source_voltage(meas.PSU_CHANNEL_NEG, V_START)
        print('  balance failed'); return None

    # 3) Final compute
    t = df['time'].to_numpy(); t_us = t*1e6; dt = t[1] - t[0]
    vs = df['V_sec'].to_numpy(); I = df['I'].to_numpy()
    burst_mask = t_us < (burst_s * 1.1) * 1e6
    B_full = np.zeros_like(vs)
    B_full[burst_mask] = np.cumsum(vs[burst_mask] * dt) / (N2 * Ae)
    p = np.polyfit(t[burst_mask], B_full[burst_mask], 1)
    B_full[burst_mask] = B_full[burst_mask] - np.polyval(p, t[burst_mask])
    B_full = virtual_close(B_full, t, i_s, i_e)
    H_full = N1 * I / le
    t_c = t[i_s:i_e]; vs_c = vs[i_s:i_e]; I_c = I[i_s:i_e]
    B_c = B_full[i_s:i_e]; H_c = H_full[i_s:i_e]
    Q       = abs((N1/N2) * trapz(I_c * vs_c, t_c))
    P_core  = Q * f
    B_peak  = (B_c.max() - B_c.min()) / 2.0
    H_peak  = (H_c.max() - H_c.min()) / 2.0
    delta_I_final = I[i_e] - I[i_s]
    I_pp_cycle = I_c.max() - I_c.min()

    if B_peak > B_SAT_LIMIT:
        print(f'  REJECT - final B_peak {B_peak*1e3:.0f}mT > SAT'); return None

    rel_B_err_final = abs(B_peak - B_target) / B_target
    if rel_B_err_final > B_REJECT_TOL:
        print(f'  REJECT - final B_peak {B_peak*1e3:.1f}mT off target '
              f'{B_target*1e3:.0f}mT by {rel_B_err_final*100:.0f}%'); return None

    print(f'  RESULT: V+={V_pos:.2f}V V-={V_neg:.2f}V  '
          f'B_pk={B_peak*1e3:.1f}mT H_pk={H_peak:.1f}A/m  '
          f'Q={Q*1e6:.2f}uJ  P={P_core*1e3:.1f}mW  driftI={delta_I_final*1e3:+.1f}mA')

    # park PSU low between cells
    meas.psu.set_source_voltage(meas.PSU_CHANNEL,     V_START)
    meas.psu.set_source_voltage(meas.PSU_CHANNEL_NEG, V_START)

    return {
        'f': f, 'B_target': B_target, 'B_peak': B_peak, 'H_peak': H_peak,
        'V_pos': V_pos, 'V_neg': V_neg,
        'Q_uJ': Q*1e6, 'P_core_mW': P_core*1e3,
        'P_density_kWm3': P_core / (Ae*le) / 1e3,
        'I_pp_mA': I_pp_cycle*1e3, 'drift_I_mA': delta_I_final*1e3,
        'BH': (H_c.copy(), B_c.copy()),
    }


def main():
    m = CoreLossMeasurement.from_config('hardware_configuration.json')
    Ae = CORE_DATABASE[CORE]['Ae']
    le = CORE_DATABASE[CORE]['le']
    L_henry = theoretical_inductance(CORE, MATERIAL, N1)

    print(f'== TPT sweep ==')
    print(f'  Core: {CORE} {MATERIAL}, N1={N1} N2={N2}, Ae={Ae*1e6:.1f}mm^2, le={le*1e3:.1f}mm')
    print(f'  L_theory = {L_henry*1e6:.1f} uH')
    print(f'  Frequencies: {[f"{f/1e3:.0f}k" for f in FREQS]}')
    print(f'  B targets:   {[f"{B*1e3:.0f}mT" for B in B_TARGETS]}')
    print(f'  Safety: V_start={V_START}V V_max={V_MAX}V '
          f'B_sat={B_SAT_LIMIT*1e3:.0f}mT I_psu_max={I_PSU_LIMIT*1e3:.0f}mA')

    rows = []; BH_data = {}
    try:
        m.psu.set_source_voltage(1, V_START); m.psu.set_source_voltage(2, V_START)
        m.psu.set_current_limit(1, 1.0);      m.psu.set_current_limit(2, 1.0)
        m.psu.enable_output(1);               m.psu.enable_output(2)

        s = m.scope
        s.set_probe_scale(m.CH_VOLTAGE,   m.input_voltage_probe_scale)
        s.set_probe_scale(m.CH_SECONDARY, m.output_voltage_probe_scale)
        s.set_probe_scale(CH_PWM,         1.0)
        s.set_probe_scale(m.CH_CURRENT,   m.current_probe_scale)
        s.set_number_samples(SAMPLES)
        apply_labels(m)
        time.sleep(0.4)

        for B_target in B_TARGETS:
            for f in FREQS:
                try:
                    res = measure_cell(m, f, B_target, Ae, le, L_henry)
                except Exception as e:
                    print(f'  EXCEPTION: {e}')
                    res = None
                if res is None:
                    rows.append({'f': f, 'B_target': B_target, 'status': 'skipped'})
                    time.sleep(0.5)  # let things settle
                    continue
                BH_data[(f, B_target)] = res.pop('BH')
                res['status'] = 'ok'
                rows.append(res)

    finally:
        m.psu.disable_output(1); m.psu.disable_output(2)
        m.close()

    df = pd.DataFrame(rows)
    df.to_csv('tpt_sweep_results.csv', index=False)
    n_ok = (df.status == 'ok').sum()
    print(f'\nSaved tpt_sweep_results.csv ({len(df)} rows, {n_ok} successful)')

    ok = df[df.status == 'ok']
    if len(ok) > 0:
        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        for B in B_TARGETS:
            sub = ok[np.isclose(ok.B_target, B, atol=1e-6)].sort_values('f')
            if len(sub) < 1: continue
            ax.loglog(sub.f / 1e3, sub.P_density_kWm3, 'o-',
                      label=f'B={B*1e3:.0f}mT', linewidth=2, markersize=8)
        ax.set_xlabel('f [kHz]'); ax.set_ylabel('P_v [kW/m^3]')
        ax.set_title(f'Core loss density - {CORE} {MATERIAL}, N1={N1} N2={N2}')
        ax.grid(True, which='both', alpha=0.3); ax.legend()
        plt.tight_layout(); plt.savefig('tpt_sweep_losses.png', dpi=120)
        print('Saved tpt_sweep_losses.png')

    if BH_data:
        n_f = len(FREQS); n_B = len(B_TARGETS)
        fig, axes = plt.subplots(n_B, n_f, figsize=(3*n_f, 3*n_B))
        if n_B == 1: axes = np.array([axes])
        if n_f == 1: axes = axes.reshape(-1, 1)
        for i, B in enumerate(B_TARGETS):
            for j, f in enumerate(FREQS):
                ax = axes[i, j]
                if (f, B) in BH_data:
                    H, Bv = BH_data[(f, B)]
                    ax.plot(H, Bv*1e3, 'C4-', lw=1.5)
                    ax.axhline(0, color='gray', lw=0.4); ax.axvline(0, color='gray', lw=0.4)
                    ax.set_title(f'{f/1e3:.0f}kHz {B*1e3:.0f}mT', fontsize=9)
                else:
                    ax.text(0.5, 0.5, '-', ha='center', va='center')
                    ax.set_title(f'{f/1e3:.0f}kHz {B*1e3:.0f}mT', fontsize=9, color='gray')
                ax.grid(alpha=0.3)
                if j == 0: ax.set_ylabel('B [mT]')
                if i == n_B-1: ax.set_xlabel('H [A/m]')
        plt.tight_layout(); plt.savefig('tpt_sweep_bh_grid.png', dpi=110)
        print('Saved tpt_sweep_bh_grid.png')


if __name__ == '__main__':
    main()
