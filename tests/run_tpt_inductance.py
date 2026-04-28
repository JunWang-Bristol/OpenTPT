#!/usr/bin/env python3
"""
Run tpt.py InductanceMeasurement on TX26/15/10-3C90 with PicoScope-specific
scope configuration overrides.
"""
import sys
import os
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/')))

from tpt import InductanceMeasurement, theoretical_inductance

CORE = "T26"
MATERIAL = "3C90"
N_TURNS = 10
VOLTAGE = 10.0
FREQUENCY = 50e3

L_theory = theoretical_inductance(CORE, MATERIAL, N_TURNS)
print(f"Theoretical L = {L_theory*1e6:.1f} uH")

meas = InductanceMeasurement.from_config("hardware_configuration.json")

# Override scope configuration for PicoScope with direct probes
# PicoScope ranges are +/- full scale, not V/div
scope = meas.scope
scope.set_channel_configuration(meas.CH_VOLTAGE, 20.0, 1, 0.0)  # +-20V, DC
scope.set_channel_label(meas.CH_VOLTAGE, "Voltage")
scope.set_channel_configuration(meas.CH_CURRENT, 1.0, 1, 0.0)   # +-1V, DC (500mA*10mV/mA=5V... but we need resolution)
scope.set_channel_label(meas.CH_CURRENT, "Current")

# Trigger at 4V on voltage channel — above DC bias, below pulse peak
scope.set_rising_trigger(meas.CH_VOLTAGE, 4.0)

# Timing
T_half = 1.0 / (2.0 * FREQUENCY)
total_time = T_half * 8
dt_target = T_half / 50.0
n_samples = 5000
scope.set_number_samples(n_samples)
scope.set_sampling_time(dt_target)

print(f"Scope: +-20V (V), +-5V (I), trigger 4V, {n_samples} samples")

# Now run _fire_and_capture and _extract_inductance manually
meas._configure_psu(VOLTAGE)
try:
    df = meas._fire_and_capture(T_half, 8)
    if df is None:
        print("Capture failed.")
        sys.exit(1)

    import numpy as np
    t = df["time"].to_numpy()
    V = df["Voltage"].to_numpy()
    I = df["Current"].to_numpy()

    print(f"\nV range: [{V.min():.3f}, {V.max():.3f}] V")
    print(f"I range: [{I.min():.4f}, {I.max():.4f}] A  pk-pk={np.ptp(I)*1e3:.1f} mA")

    L = meas._extract_inductance(t, V, I, VOLTAGE)
    if L is not None:
        err = (L - L_theory) / L_theory * 100
        print(f"\n>>> L = {L*1e6:.1f} uH  (theory: {L_theory*1e6:.0f} uH, error: {err:+.1f}%)")
    else:
        print("\nExtraction failed.")
finally:
    meas._disable_psu()
