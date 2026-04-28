"""Simple hardware connectivity test for OpenTPT.

Tests:
1. PSU connection and identification
2. Oscilloscope connection
3. Board (NUCLEO) connection and pulse generation
4. Capture pulses on the scope through the 47 ohm resistor
"""

import sys
import time
import json
import numpy as np
import matplotlib.pyplot as plt

from power_supply import PowerSupply
from oscilloscope import Oscilloscope
from board import Board


def main():
    # Load configuration
    with open("../hardware_configuration.json") as f:
        cfg = json.load(f)

    print("=" * 60)
    print("OpenTPT Hardware Connectivity Test")
    print("=" * 60)

    # ─── Test PSU ─────────────────────────────────────────────────────────────
    print("\n[1] Testing Power Supply...")
    try:
        psu = PowerSupply.factory(cfg["power_supply"], cfg["power_supply_port"])
        print(f"    PSU connected: {cfg['power_supply']} on {cfg['power_supply_port']}")
        # Try to read current voltage
        try:
            voltages = psu.get_all_source_voltages()
            print(f"    Current voltages: {voltages}")
        except Exception as e:
            print(f"    (Could not read voltages: {e})")
        print("    PSU: OK")
    except Exception as e:
        print(f"    PSU: FAILED - {e}")
        return

    # ─── Test Oscilloscope ────────────────────────────────────────────────────
    print("\n[2] Testing Oscilloscope...")
    try:
        scope = Oscilloscope.factory(cfg["oscilloscope"], cfg["oscilloscope_port"])
        print(f"    Scope connected: {cfg['oscilloscope']} on {cfg['oscilloscope_port']}")
        print(f"    Number of channels: {scope.get_number_channels()}")
        print(f"    Available voltage ranges: {scope.get_input_voltage_ranges()}")
        print("    Scope: OK")
    except Exception as e:
        print(f"    Scope: FAILED - {e}")
        return

    # ─── Test Board ───────────────────────────────────────────────────────────
    print("\n[3] Testing NUCLEO Board...")
    try:
        board = Board.factory(cfg["board"], cfg["board_port"])
        print(f"    Board connected: {cfg['board']} on {cfg['board_port']}")
        try:
            idn = board.get_identification()
            print(f"    Identification: {idn.strip()}")
        except Exception as e:
            print(f"    (Could not get ID: {e})")
        try:
            version = board.get_version()
            print(f"    Firmware version: {version.strip()}")
        except Exception as e:
            print(f"    (Could not get version: {e})")
        try:
            min_period = board.get_minimum_period()
            max_period = board.get_maximum_period()
            print(f"    Pulse period range: {min_period*1e6:.1f} us - {max_period*1e3:.1f} ms")
        except Exception as e:
            print(f"    (Could not get period range: {e})")
        print("    Board: OK")
    except Exception as e:
        print(f"    Board: FAILED - {e}")
        return

    # ─── Test Pulse Capture ───────────────────────────────────────────────────
    print("\n[4] Testing Pulse Capture (PSU -> 47 ohm resistor -> Scope CH1)...")
    
    # Set PSU to 5V on channel 1
    TEST_VOLTAGE = 5.0
    TEST_FREQ = 10000  # 10 kHz
    T_HALF = 1.0 / (2.0 * TEST_FREQ)  # 50 us half-period
    NUM_PULSES = 8

    print(f"    Setting PSU CH1 to {TEST_VOLTAGE} V...")
    try:
        psu.set_source_voltage(1, TEST_VOLTAGE)
        psu.set_current_limit(1, 0.5)  # 500 mA limit for safety
        psu.enable_output(1)
        time.sleep(0.5)  # Let it stabilize
        print(f"    PSU output enabled")
    except Exception as e:
        print(f"    PSU setup failed: {e}")
        return

    # Configure scope
    # Note: probe_scale is 50 in config, but for a direct 47 ohm resistor test
    # we should use scale=1 (no attenuation)
    # The voltage across the resistor will be close to the PSU voltage
    print(f"    Configuring scope CH1 (expecting ~{TEST_VOLTAGE} V pulses)...")
    try:
        # Use 10V range to capture 5V pulses with headroom
        # Coupling: 1 = DC, 0 = AC
        scope.set_channel_configuration(0, 10.0, 1, 0.0)  # CH A, 10V range, DC coupling
        scope.set_channel_label(0, "Voltage")
        # Don't apply probe scale for direct measurement
        scope.set_probe_scale(0, 1.0)
        
        # Set trigger at 30% of expected voltage, rising edge
        trigger_level = TEST_VOLTAGE * 0.3
        scope.set_rising_trigger(0, trigger_level, timeout=5000)  # 5s auto-trigger timeout
        
        # Configure timing: 50 samples per half-period, capture full burst
        total_time = T_HALF * NUM_PULSES * 1.5
        dt_target = T_HALF / 50.0
        n_samples = max(500, int(total_time / dt_target))
        scope.set_number_samples(n_samples)
        scope.set_sampling_time(dt_target)
        
        print(f"    Scope configured: trigger={trigger_level:.2f}V, samples={n_samples}, dt={dt_target*1e6:.2f}us")
    except Exception as e:
        print(f"    Scope setup failed: {e}")
        psu.disable_output(1)
        return

    # Load pulses onto board
    print(f"    Loading {NUM_PULSES} pulses (T_half={T_HALF*1e6:.1f} us) onto board...")
    try:
        board.clear_pulses()
        for _ in range(NUM_PULSES):
            board.add_pulse(T_HALF)
        pulses = board.read_pulses()
        print(f"    Pulses loaded: {len(pulses)} pulses")
    except Exception as e:
        print(f"    Board pulse setup failed: {e}")
        psu.disable_output(1)
        return

    # Arm scope and fire pulses
    print("    Starting acquisition and firing pulses...")
    try:
        scope.run_acquisition_block()
        time.sleep(0.1)  # Small delay to ensure scope is armed
        
        board.run_pulses(1)
        
        # Read data (PicoScope blocks until complete)
        df = scope.read_data([0])
        
        if df is None or df.empty:
            print("    ERROR: No data captured!")
            psu.disable_output(1)
            return
            
        print(f"    Data captured: {len(df)} samples")
        
        t = df["time"].to_numpy()
        V = df["Voltage"].to_numpy()
        
        print(f"    Voltage range: [{V.min():.3f}, {V.max():.3f}] V")
        print(f"    Time span: {t[-1]*1e6:.1f} us")
        
    except Exception as e:
        print(f"    Capture failed: {e}")
        psu.disable_output(1)
        return
    finally:
        psu.disable_output(1)
        print("    PSU output disabled")

    # Plot results
    print("\n[5] Plotting captured waveform...")
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(t * 1e6, V, linewidth=1.0, color="tab:blue")
    ax.set_xlabel("Time (us)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title(f"Pulse Capture Test - {NUM_PULSES} pulses at {TEST_FREQ/1e3:.1f} kHz")
    ax.grid(True, alpha=0.4)
    ax.axhline(y=TEST_VOLTAGE, color='r', linestyle='--', alpha=0.5, label=f'Expected: {TEST_VOLTAGE}V')
    ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
    ax.legend()
    plt.tight_layout()
    plt.savefig("../test_capture.png", dpi=150)
    print("    Plot saved to test_capture.png")
    plt.show()

    print("\n" + "=" * 60)
    print("Hardware test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
