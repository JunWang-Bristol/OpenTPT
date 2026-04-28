#!/usr/bin/env python3
"""
Hardware Diagnostic for Core Loss Setup
========================================
Validates connections before running full core loss measurement:
  1. PSU voltage output
  2. Board pulse generation
  3. Scope trigger capture

Usage:
  python diagnostic_core_loss.py
"""

import sys
import os
import time
import json
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from power_supply import PowerSupply
from oscilloscope import Oscilloscope
from board import Board

CONFIG = "hardware_configuration.json"

print("=" * 70)
print("  Core Loss Setup Diagnostic")
print("=" * 70)

# ── Connect hardware ─────────────────────────────────────────────────────────
print("\n[1] Connecting hardware...")
with open(CONFIG) as f:
    cfg = json.load(f)

psu = PowerSupply.factory(cfg['power_supply'], cfg['power_supply_port'])
scope = Oscilloscope.factory(cfg['oscilloscope'], cfg['oscilloscope_port'])
board = Board.factory(cfg['board'], cfg['board_port'])

print(f"    Board: {board.get_identification().strip()}")
print(f"    PSU: {psu.get_version()}")
print(f"    Scope: {type(scope).__name__}")

# ── Test PSU ─────────────────────────────────────────────────────────────────
print("\n[2] Testing PSU output...")
TEST_VOLTAGE = 5.0
psu.set_source_voltage(1, TEST_VOLTAGE)
psu.set_current_limit(1, 0.5)
psu.enable_output(1)
time.sleep(1)

meas_v = psu.get_measured_voltage(1)
meas_i = psu.get_measured_current(1)
print(f"    Set: {TEST_VOLTAGE} V")
print(f"    Measured: {meas_v:.2f} V  {meas_i*1e3:.2f} mA")

if abs(meas_v - TEST_VOLTAGE) > 0.5:
    print("    WARNING: PSU voltage mismatch — check connections")
if meas_i < 0.001:
    print("    WARNING: No current flow — check inductor connection")
else:
    print("    OK: Current flowing")

# ── Test single pulse ────────────────────────────────────────────────────────
print("\n[3] Testing single pulse capture...")
T_HALF = 10e-6  # 10 us

# Configure scope
scope.set_channel_configuration(0, 2.0, "DC", 0.0)   # Ch1: voltage
scope.set_channel_configuration(2, 0.2, "DC", 0.0)   # Ch3: current
scope.set_channel_label(0, "Voltage")
scope.set_channel_label(2, "Current")

# Trigger on voltage (should see input pulse)
scope.set_rising_trigger(0, TEST_VOLTAGE * 0.2)

# Short acquisition
scope.set_number_samples(1000)
scope.set_sampling_time(100e-9)  # 100 ns/sample

# Fire single pulse
board.clear_pulses()
board.add_pulse(T_HALF)
board.add_pulse(T_HALF)

acq_time = scope.number_samples * scope.sampling_time
scope.set_acquisition_time(acq_time)
scope.start_single_acquisition()
time.sleep(2)

board.run_pulses(1)

# Poll for completion
deadline = time.monotonic() + 10.0
while True:
    time.sleep(0.1)
    state = scope.get_acquisition_state()
    if state == "COMP":
        break
    if time.monotonic() > deadline:
        print("    ERROR: Scope timeout — trigger not detected")
        print("    Check:")
        print("      - Voltage probe connected to Ch1")
        print("      - Probe ground connected to board ground")
        print("      - Pulse output connected to inductor")
        break
else:
    print("    Acquisition complete!")
    
    # Read data
    df = scope.read_data([0, 2])
    V = df["Voltage"].to_numpy()
    I = df["Current"].to_numpy()
    t = df["time"].to_numpy()
    
    print(f"    Voltage range: [{V.min():.2f}, {V.max():.2f}] V")
    print(f"    Current range: [{I.min()*1e3:.2f}, {I.max()*1e3:.2f}] mA")
    
    if np.ptp(V) < 0.1:
        print("    WARNING: No voltage pulse detected")
    else:
        print("    OK: Pulse detected")

# ── Cleanup ──────────────────────────────────────────────────────────────────
print("\n[4] Cleanup...")
psu.disable_output(1)
board.close()

print("\n" + "=" * 70)
print("  Diagnostic complete")
print("=" * 70)
