"""Single careful capture at 50 kHz with current calibration.

Goals:
  - Verify probe scales (now 1 in config) give physically-plausible numbers
  - Confirm V_pri pp <= 2*V_supply (no inflation)
  - Confirm B_peak < 350 mT (no saturation/inflation)
  - Use a safe small voltage (1V) to avoid saturation at low f
"""
import os, sys, time
sys.path.insert(0, 'src')

import numpy as np
from tpt import CoreLossMeasurement, theoretical_inductance, CORE_DATABASE


CORE = "T26"
N1, N2 = 10, 1
F = 50_000        # 50 kHz - mid-range, well-tested
VOLTAGE = 1.0     # SAFE low voltage to avoid saturation
N_HALF = 8
T_HALF = 1.0 / (2.0 * F)
CH_PWM = 2


def main():
    m = CoreLossMeasurement.from_config('hardware_configuration.json')
    Ae = CORE_DATABASE[CORE]['Ae']
    le = CORE_DATABASE[CORE]['le']
    L_th = theoretical_inductance(CORE, '3C90', N1)

    print(f'== Investigation: single capture at {F/1e3:.0f} kHz, V={VOLTAGE} V ==')
    print(f'  Probe scales (from config): V_pri={m.input_voltage_probe_scale}  '
          f'V_sec={m.output_voltage_probe_scale}  I={m.current_probe_scale}')
    print(f'  Core: {CORE}, N1={N1} N2={N2}, Ae={Ae*1e6:.1f}mm^2, le={le*1e3:.1f}mm')
    print(f'  L_theory = {L_th*1e6:.1f} uH')
    print(f'  Expected steady-state ripple at V={VOLTAGE}V: '
          f'dI = V*T_half/L = {VOLTAGE*T_HALF/L_th*1e3:.1f} mA pp')
    print(f'  Expected B_peak: V*T_half/(2*N1*Ae) = '
          f'{VOLTAGE*T_HALF/(2*N1*Ae)*1e3:.2f} mT')
    print(f'  (or with N2 in formula:  V*T_half/(2*N2*Ae) = '
          f'{VOLTAGE*T_HALF/(2*N2*Ae)*1e3:.1f} mT for N2=1 secondary)')

    try:
        m.psu.set_source_voltage(1, VOLTAGE); m.psu.set_source_voltage(2, VOLTAGE)
        m.psu.set_current_limit(1, 1.0);     m.psu.set_current_limit(2, 1.0)   # 1A safety limit
        m.psu.enable_output(1);              m.psu.enable_output(2)
        time.sleep(0.4)
        v1 = m.psu.get_measured_voltage(1); v2 = m.psu.get_measured_voltage(2)
        i1 = m.psu.get_measured_current(1); i2 = m.psu.get_measured_current(2)
        print(f'  PSU at idle: CH1 V={v1:.3f}V I={i1*1e3:.1f}mA   CH2 V={v2:.3f}V I={i2*1e3:.1f}mA')
        if i1 > 0.5 or i2 > 0.5:
            print('  WARNING: idle current > 500 mA, board may have a short')

        m.board.clear_pulses()
        for _ in range(N_HALF):
            m.board.add_pulse(T_HALF)

        s = m.scope
        s.set_probe_scale(m.CH_VOLTAGE,   m.input_voltage_probe_scale)
        s.set_probe_scale(m.CH_SECONDARY, m.output_voltage_probe_scale)
        s.set_probe_scale(CH_PWM,         1.0)   # PWM probe also at 1x
        s.set_probe_scale(m.CH_CURRENT,   m.current_probe_scale)
        # Wide ranges to avoid clipping (we now KNOW probes are 1x and PSU is 1V)
        s.set_channel_configuration(m.CH_VOLTAGE,   5.0, 'DC', 0.0)
        s.set_channel_configuration(m.CH_SECONDARY, 5.0, 'DC', 0.0)
        s.set_channel_configuration(CH_PWM,         5.0, 'DC', 0.0)
        s.set_channel_configuration(m.CH_CURRENT,   0.1, 'DC', 0.0)
        s.set_channel_label(m.CH_VOLTAGE,   'V_pri')
        s.set_channel_label(m.CH_SECONDARY, 'V_sec')
        s.set_channel_label(CH_PWM,         'PWM')
        s.set_channel_label(m.CH_CURRENT,   'I')
        s.set_rising_trigger(CH_PWM, 0.5, timeout=0)
        s.set_number_samples(2000)
        s.set_sampling_time(100e-9)

        print('\nFiring single 8-pulse burst...')
        s.start_single_acquisition()
        time.sleep(1.5)
        m.board.run_pulses(1)
        deadline = time.monotonic() + 6
        while True:
            st = s.get_acquisition_state()
            if st == 'COMP': break
            if time.monotonic() > deadline:
                print(f'TIMEOUT (state={st})')
                return
            time.sleep(0.1)
        df = s.read_data([m.CH_VOLTAGE, m.CH_SECONDARY, CH_PWM, m.CH_CURRENT])

        # PSU loaded current
        time.sleep(0.05)
        i1 = m.psu.get_measured_current(1)
        i2 = m.psu.get_measured_current(2)
        print(f'  PSU during/after burst: CH1 I={i1*1e3:.1f}mA   CH2 I={i2*1e3:.1f}mA')

        # Analyse
        t = df['time'].to_numpy() * 1e6
        vp  = df['V_pri'].to_numpy()
        vs  = df['V_sec'].to_numpy()
        pwm = df['PWM'].to_numpy()
        I   = df['I'].to_numpy()

        print(f'\n--- Captured signal magnitudes ---')
        print(f'  V_pri:  min={vp.min():+6.3f}  max={vp.max():+6.3f}  pp={vp.max()-vp.min():.3f} V')
        print(f'  V_sec:  min={vs.min():+6.3f}  max={vs.max():+6.3f}  pp={vs.max()-vs.min():.3f} V')
        print(f'  PWM:    min={pwm.min():+6.3f}  max={pwm.max():+6.3f}')
        print(f'  I:      min={I.min()*1e3:+6.2f}  max={I.max()*1e3:+6.2f}  pp={(I.max()-I.min())*1e3:.2f} mA')

        # Sanity checks
        print(f'\n--- Sanity checks ---')
        print(f'  V_pri pp expected <= 2*V = {2*VOLTAGE:.2f}V (real)  --  measured pp = {vp.max()-vp.min():.2f}V')
        if (vp.max() - vp.min()) > 4 * VOLTAGE:
            print(f'  *** V_pri pp is > 4x V_supply -- still scaling issue?')
        else:
            print(f'  *** V_pri pp looks OK')

        # Find PWM edges and compute B_peak on target cycle
        above = pwm > 1.0
        rising  = np.where((~above[:-1]) & above[1:])[0] + 1
        falling = np.where(above[:-1] & (~above[1:]))[0] + 1
        print(f'\n  PWM rising edges: {len(rising)}, falling: {len(falling)}')
        if len(rising) >= 2:
            gaps = np.diff(rising) * (t[1] - t[0])
            print(f'  Edge spacing (us): mean={gaps.mean():.2f}  expected = {1e6/F:.2f} us (full cycle)')

        # Quick BH compute on a single cycle
        if len(rising) >= 2 and len(falling) >= 1:
            i_start = int(rising[-2])
            falls_after = falling[falling > i_start]
            i_mid = int(falls_after[0]) if len(falls_after) else None
            rises_after = rising[rising > i_mid] if i_mid else np.array([])
            i_end = int(rises_after[0]) if len(rises_after) else len(t) - 1
            dt = (t[1] - t[0]) * 1e-6
            B = np.cumsum(vs * dt) / (N2 * Ae)
            B = B - np.linspace(B[0], B[-1], len(B))   # simple drift remove
            B_c = B[i_start:i_end]
            B_peak = (B_c.max() - B_c.min()) / 2.0 if len(B_c) > 1 else 0
            I_c = I[i_start:i_end]
            I_pp = (I_c.max() - I_c.min()) if len(I_c) > 1 else 0
            print(f'\n  Target cycle: t={t[i_start]:.2f}..{t[i_end]:.2f}us')
            print(f'  Measured B_peak (half swing): {B_peak*1e3:.2f} mT')
            print(f'  Measured I_pp:                {I_pp*1e3:.2f} mA')
            print(f'  Expected B_peak (V*T_half/(2*N2*Ae)) = '
                  f'{VOLTAGE*T_HALF/(2*N2*Ae)*1e3:.2f} mT')
            print(f'  Expected I_pp (V*T_half/L)           = '
                  f'{VOLTAGE*T_HALF/L_th*1e3:.2f} mA')

            ratio_B = B_peak / (VOLTAGE*T_HALF/(2*N2*Ae))
            ratio_I = I_pp / (VOLTAGE*T_HALF/L_th)
            print(f'\n  B_measured/B_expected = {ratio_B:.2f}  (1.0 = perfect)')
            print(f'  I_measured/I_expected = {ratio_I:.2f}')

    finally:
        m.psu.disable_output(1); m.psu.disable_output(2)
        m.close()
        print('\nPSU disabled. Done.')


if __name__ == '__main__':
    main()
