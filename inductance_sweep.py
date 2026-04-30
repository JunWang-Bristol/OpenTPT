"""Inductance vs flux excursion - saturation curve.

For each PSU voltage V, fires N_HALF symmetric pulses at fixed F and
measures inductance two ways:

  L_dV  = V_pri_avg * T_half / dI_pp   (peak-to-peak slope, robust)
  L_fit = V_pri_avg / fit_slope(I)      (least-squares on the ramp)

Then plots L vs measured B_peak (B_peak = V_pri_avg * T_half / (2 * N1 * Ae)).

Pattern:
  - PWM triggering (channel 2, rail-to-rail logic from MCU) - reliable at
    every voltage including very low V_pri.
  - Coarse-then-narrow scope auto-ranging on V_pri and I.
  - PSU current safety abort.
  - Auto-stop when L_dV drops below L_DROP_REJECT * baseline (saturation).

Outputs:
  - inductance_sweep_results.csv
  - inductance_sweep.png  (L vs B_peak, both estimates)
"""
import os, sys, time
sys.path.insert(0, 'src')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from tpt import CoreLossMeasurement, theoretical_inductance, CORE_DATABASE


# ---------- configuration ----------
CORE          = "T26"
MATERIAL      = "3C90"
N1            = 10
F             = 25e3              # low f -> high B per volt; reaches saturation
N_HALF        = 8
SAMPLES       = 2500
CH_PWM        = 2
V_LIST        = [0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 9.0, 11.0]
# Safety guards — saturation produces high inductor current and PSU draw,
# heats the windings/MOSFETs. Multiple aborts triggered well before damage.
I_PSU_LIMIT   = 0.20    # PSU per-channel current trip (was 0.30; tightened)
DI_PP_LIMIT   = 0.50    # hard cap on inductor di_pp during burst [A]
L_DROP_REJECT = 0.6     # stop when L drops to 60% of baseline (catches knee earlier)
PSU_CURRENT_LIMIT_SETTING = 0.5  # set BK current trip on each rail [A]
COOLDOWN_S    = 1.0     # between cells, let the core dissipate

V_RANGES = [0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]
I_RANGES = [0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0]


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


def psu_currents(psu):
    try:
        return psu.get_measured_current(1), psu.get_measured_current(2)
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
    """Coarse capture, narrow ranges, re-capture. Returns (df_narrow, peaks, psu_I)."""
    meas.psu.set_source_voltage(meas.PSU_CHANNEL,     V)
    meas.psu.set_source_voltage(meas.PSU_CHANNEL_NEG, V)
    time.sleep(0.25)
    s = meas.scope
    s.set_sampling_time(sample_dt)
    configure_ranges(meas, V_RANGES[-1], V_RANGES[-1], I_RANGES[-1])
    df = fire_and_capture(meas, pulses_s)
    if df is None:
        return None, None, None
    vp_peak = float(np.abs(df['V_pri']).max())
    vs_peak = float(np.abs(df['V_sec']).max())
    i_peak  = float(np.abs(df['I']).max())
    rv  = pick_smallest_range(vp_peak, V_RANGES, meas.input_voltage_probe_scale)
    rsv = pick_smallest_range(vs_peak, V_RANGES, meas.output_voltage_probe_scale)
    ri  = pick_smallest_range(i_peak,  I_RANGES, meas.current_probe_scale)
    configure_ranges(meas, rv, rsv, ri)
    df2 = fire_and_capture(meas, pulses_s)
    if df2 is None:
        return None, None, None
    Ich1, Ich2 = psu_currents(meas.psu)
    peaks = dict(vp=vp_peak, vs=vs_peak, i=i_peak, rv=rv, rsv=rsv, ri=ri)
    return df2, peaks, (Ich1, Ich2)


def get_target_cycle(df):
    pwm = df['PWM'].to_numpy()
    rising, falling = find_pwm_edges(pwm)
    if len(rising) < 2: return None, None, None
    i_start = int(rising[-2])
    falls_after = falling[falling > i_start]
    if not len(falls_after): return None, None, None
    i_mid = int(falls_after[0])
    rises_after = rising[rising > i_mid]
    i_end = int(rises_after[0]) if len(rises_after) else len(pwm) - 1
    return i_start, i_mid, i_end


def measure_L(meas, V, F, Ae):
    """Returns dict with L_dV, L_fit, B_peak_meas, V_pri_avg, dI_pp, psu_I, etc."""
    T_half = 1.0 / (2.0 * F)
    pulses_s = [T_half] * N_HALF
    burst_s = T_half * N_HALF
    sample_dt = max(20e-9, burst_s * 1.5 / SAMPLES)
    for x in [20e-9, 50e-9, 100e-9, 200e-9, 500e-9, 1e-6, 2e-6]:
        if x >= sample_dt:
            sample_dt = x; break

    df, peaks, psu_I = probe_at_voltage(meas, V, pulses_s, sample_dt)
    if df is None:
        return None

    i_s, i_mid, i_end = get_target_cycle(df)
    if i_s is None:
        return None

    t  = df['time'].to_numpy()
    vp = df['V_pri'].to_numpy()
    vs = df['V_sec'].to_numpy()
    I  = df['I'].to_numpy()

    # Positive half-cycle window (PWM high)
    pos = slice(i_s, i_mid)
    if i_mid - i_s < 5:
        return None
    V_pri_avg = float(vp[pos].mean())
    if abs(V_pri_avg) < 0.02:
        return None

    # Method 1: peak-to-peak ΔI on positive half
    I_pos = I[pos]
    dI_pp = float(I_pos.max() - I_pos.min())
    L_dV = abs(V_pri_avg) * T_half / max(dI_pp, 1e-6)

    # Method 2: linear fit dI/dt on middle 60% of positive half (avoid edge ringing)
    n = i_mid - i_s
    margin = max(2, n // 5)
    fit_sl = slice(i_s + margin, i_mid - margin)
    if fit_sl.stop - fit_sl.start < 5:
        L_fit = None
    else:
        tw = t[fit_sl]; Iw = I[fit_sl]
        tc = tw - tw.mean()
        denom = float(np.sum(tc**2))
        slope = float(np.sum(tc * (Iw - Iw.mean())) / denom) if denom > 1e-30 else 0.0
        L_fit = abs(V_pri_avg / slope) if abs(slope) > 1.0 else None

    # B_peak from APPLIED voltage (clean — avoids un-calibrated V_sec sense path):
    #   B_peak ≈ V_pri_avg · T_half / (2 · N1 · Ae)
    # The V_sec integration would give the same answer if the secondary were
    # well-calibrated; for a pure inductance test V_pri is the direct quantity.
    B_peak = abs(V_pri_avg) * T_half / (2.0 * N1 * Ae)

    return dict(
        L_dV=L_dV, L_fit=L_fit, B_peak=B_peak, V_pri_avg=V_pri_avg,
        dI_pp=dI_pp, psu_I=psu_I, peaks=peaks,
    )


def main():
    m = CoreLossMeasurement.from_config('hardware_configuration.json')
    Ae = CORE_DATABASE[CORE]['Ae']
    le = CORE_DATABASE[CORE]['le']
    L_th = theoretical_inductance(CORE, MATERIAL, N1)
    T_half = 1.0 / (2.0 * F)

    print(f'== Inductance sweep ==')
    print(f'  Core: {CORE} {MATERIAL}, N1={N1}, Ae={Ae*1e6:.1f}mm^2, le={le*1e3:.1f}mm')
    print(f'  L_theory  = {L_th*1e6:.1f} uH')
    print(f'  Frequency = {F/1e3:.0f} kHz, T_half = {T_half*1e6:.2f} us')
    print(f'  V grid    = {V_LIST}')
    B_max_th = V_LIST[-1] * T_half / (2.0 * N1 * Ae) * 1e3
    print(f'  Max B (th) at V={V_LIST[-1]}V: ~{B_max_th:.0f} mT  (3C90 sat ~250 mT)')
    print(f'  Safety guards:')
    print(f'    PSU current trip   : {PSU_CURRENT_LIMIT_SETTING*1e3:.0f} mA per rail (HW cutoff)')
    print(f'    PSU current abort  : {I_PSU_LIMIT*1e3:.0f} mA  (sweep abort)')
    print(f'    dI_pp hard cap     : {DI_PP_LIMIT*1e3:.0f} mA  (sweep abort)')
    print(f'    L drop sat-stop    : <{L_DROP_REJECT*100:.0f}% of baseline')
    print(f'    Cooldown per cell  : {COOLDOWN_S:.1f} s')

    rows = []
    L_baseline = None
    try:
        m.psu.set_source_voltage(1, V_LIST[0]); m.psu.set_source_voltage(2, V_LIST[0])
        m.psu.set_current_limit(1, PSU_CURRENT_LIMIT_SETTING)
        m.psu.set_current_limit(2, PSU_CURRENT_LIMIT_SETTING)
        m.psu.enable_output(1);                 m.psu.enable_output(2)

        s = m.scope
        s.set_probe_scale(m.CH_VOLTAGE,   m.input_voltage_probe_scale)
        s.set_probe_scale(m.CH_SECONDARY, m.output_voltage_probe_scale)
        s.set_probe_scale(CH_PWM,         1.0)
        s.set_probe_scale(m.CH_CURRENT,   m.current_probe_scale)
        s.set_number_samples(SAMPLES)
        apply_labels(m)
        time.sleep(0.4)

        for V in V_LIST:
            B_th = V * T_half / (2.0 * N1 * Ae)
            print(f'\n--- V = {V:.2f} V   (expected B_peak ~ {B_th*1e3:.2f} mT) ---')
            try:
                r = measure_L(m, V, F, Ae)
            except Exception as e:
                print(f'  EXCEPTION: {e!r}')
                r = None
            if r is None:
                rows.append({'V_set': V, 'B_th_mT': B_th*1e3, 'status': 'failed'})
                continue

            L_dV  = r['L_dV']  * 1e6
            L_fit = r['L_fit'] * 1e6 if r['L_fit'] else None
            B_pk  = r['B_peak'] * 1e3
            I1, I2 = r['psu_I']

            print(f'  V_pri_avg = {r["V_pri_avg"]:.3f} V   dI_pp = {r["dI_pp"]*1e3:.2f} mA   '
                  f'B_meas = {B_pk:.2f} mT')
            print(f'  L_dV = {L_dV:.1f} uH   L_fit = '
                  f'{(f"{L_fit:.1f}" if L_fit else "n/a")} uH   '
                  f'(L_th = {L_th*1e6:.1f} uH)   PSU I = {I1*1e3:.0f}/{I2*1e3:.0f} mA')

            if L_baseline is None:
                L_baseline = r['L_dV']
            ratio = r['L_dV'] / L_baseline

            rows.append({
                'V_set': V, 'V_pri_avg': r['V_pri_avg'],
                'B_th_mT': B_th*1e3, 'B_meas_mT': B_pk,
                'dI_pp_mA': r['dI_pp']*1e3,
                'L_dV_uH': L_dV, 'L_fit_uH': L_fit,
                'L_ratio': ratio,
                'I_psu1_mA': I1*1e3, 'I_psu2_mA': I2*1e3,
                'status': 'ok',
            })

            if max(abs(I1), abs(I2)) > I_PSU_LIMIT:
                print(f'  PSU current {max(abs(I1),abs(I2))*1e3:.0f}mA > {I_PSU_LIMIT*1e3:.0f}mA limit -- aborting sweep')
                break
            if r['dI_pp'] > DI_PP_LIMIT:
                print(f'  dI_pp {r["dI_pp"]*1e3:.0f}mA > {DI_PP_LIMIT*1e3:.0f}mA hard cap '
                      f'(deep saturation) -- aborting sweep')
                break
            if ratio < L_DROP_REJECT:
                print(f'  L_dV dropped to {ratio*100:.0f}% of baseline -- saturation knee, stopping')
                break

            # Park PSU low between cells, let core dissipate
            m.psu.set_source_voltage(m.PSU_CHANNEL,     V_LIST[0])
            m.psu.set_source_voltage(m.PSU_CHANNEL_NEG, V_LIST[0])
            time.sleep(COOLDOWN_S)

    finally:
        try: m.psu.disable_output(1); m.psu.disable_output(2)
        except Exception: pass
        m.close()

    df = pd.DataFrame(rows)
    df.to_csv('inductance_sweep_results.csv', index=False)
    n_ok = (df.status == 'ok').sum()
    print(f'\nSaved inductance_sweep_results.csv ({len(df)} rows, {n_ok} successful)')

    ok = df[df.status == 'ok']
    if len(ok) >= 1:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.semilogx(ok.B_meas_mT, ok.L_dV_uH, 'o-', color='C0',
                    linewidth=2, markersize=9, label='L (dI_pp method)')
        if ok.L_fit_uH.notna().any():
            sub = ok[ok.L_fit_uH.notna()]
            ax.semilogx(sub.B_meas_mT, sub.L_fit_uH, 's--', color='C1',
                        linewidth=1.4, markersize=7, label='L (linear-fit method)')
        ax.axhline(L_th*1e6, color='gray', linestyle='--', linewidth=1.4,
                   label=f'L_theory = {L_th*1e6:.0f} uH')
        ax.axhline(L_th*1e6 * L_DROP_REJECT, color='red', linestyle=':',
                   linewidth=1.0, label=f'{L_DROP_REJECT*100:.0f}% threshold')
        ax.set_xlabel('Measured B_peak [mT]')
        ax.set_ylabel('L [uH]')
        ax.set_title(f'Inductance vs flux excursion - {CORE} {MATERIAL}, '
                     f'N1={N1}, f={F/1e3:.0f}kHz')
        ax.grid(True, which='both', alpha=0.3); ax.legend(loc='lower left')
        plt.tight_layout(); plt.savefig('inductance_sweep.png', dpi=120)
        print('Saved inductance_sweep.png')


if __name__ == '__main__':
    main()
