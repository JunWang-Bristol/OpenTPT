#!/usr/bin/env python3
"""
Core Loss Measurement — 10-turn inductor
=========================================
Setup:
  - Magnetic: 10 turns (N1=10)
  - Current probe: 10 mA/mV = 100 mV/A (current_probe_scale = 0.1)
  - Voltage probe grounds: connected to board ground
  - Ch1 (CH_VOLTAGE): input voltage (primary)
  - Ch2 (CH_SECONDARY): output voltage (secondary sense winding)
  - Ch3 (CH_CURRENT): inductor current

Usage:
  python measure_core_loss_10turn.py
"""

import sys
import os
import time

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from tpt import CoreLossMeasurement, flux_to_voltage

# ── User parameters ──────────────────────────────────────────────────────────

CORE_NAME = "T26"          # Toroid from CORE_DATABASE (T18, T26, E32, E42)
N1 = 10                    # Primary winding turns
N2 = 1                     # Secondary sense winding turns
FREQUENCY = 50_000         # Hz (50 kHz)
TARGET_B_PEAK_mT = 100     # Target peak flux density [mT]

# For flux targeting: measure_core_loss will iteratively adjust voltage
# to hit the requested B_peak.  If you want a fixed voltage instead, set
# VOLTAGE and comment out target_B_peak_T below.
VOLTAGE = 10.0             # Starting PSU voltage [V]

# ── Hardware configuration ───────────────────────────────────────────────────

# Read hardware config
config_path = os.path.join(os.path.dirname(__file__), 'hardware_configuration.json')

print("=" * 70)
print("  Core Loss Measurement — 10-turn inductor")
print(f"  Core: {CORE_NAME}  N1={N1}  N2={N2}")
print(f"  Frequency: {FREQUENCY/1e3:.0f} kHz  Target B_peak: {TARGET_B_PEAK_mT} mT")
print("=" * 70)

# Create measurement instance with probe scales
meas = CoreLossMeasurement.from_config(config_path)

# The scope channel assignments are:
#   CH_VOLTAGE   = 0  (Ch1) — primary/input voltage
#   CH_SECONDARY = 1  (Ch2) — secondary winding voltage
#   CH_CURRENT   = 2  (Ch3) — inductor current

print("\n[1] Hardware connected:")
print(f"    Board ID: {meas.board.get_identification().strip()}")
print(f"    PSU: {meas.psu.get_version()}")
print(f"    Scope: {type(meas.scope).__name__}")

print("\n[2] Running core loss measurement...")
print("    This may take a minute (flux targeting + balancing + capture)")

result = meas.measure_core_loss(
    voltage         = VOLTAGE,
    frequency       = FREQUENCY,
    N1              = N1,
    N2              = N2,
    core_name       = CORE_NAME,
    L_henry         = None,          # No inductance estimate (skip balancing)
    dc_bias_A       = 0.0,
    plot            = True,
    save_csv        = "core_loss_10turn.csv",
    target_B_peak_T = TARGET_B_PEAK_mT * 1e-3,  # Convert mT to T
    balance         = False,         # Skip volt-second balancing (no L estimate)
)

if result:
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print(f"  Core loss power:  {result['P_core']*1e3:.2f} mW")
    print(f"  B_peak:           {result['B_peak']*1e3:.1f} mT")
    print(f"  H_peak:           {result['H_peak']:.0f} A/m")
    print(f"  Energy/cycle:     {result['Q_cycle']*1e6:.2f} uJ")
    if result['P_density'] > 0:
        print(f"  Power density:    {result['P_density']/1e3:.1f} kW/m^3")
    print(f"\n  Waveform saved to: core_loss_10turn.csv")
    print("=" * 70)
else:
    print("\n  ERROR: Measurement failed (check connections and trigger)")

# Clean up
meas.close()
print("\nDone.")
