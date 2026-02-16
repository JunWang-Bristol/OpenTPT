# TPT Pulse Train Test Walkthrough and Troubleshooting

**Date:** 2026-02-11
**Script:** `tests/test_tpt_pulse_train.py`

This guide explains how to use the pulse train test script and documents a critical fix for pulse train persistence.

## 1. Overview
The `test_tpt_pulse_train.py` script allows you to:
1. Define a sequence of pulses (periods in seconds)
2. Load them into the NUCLEO-H503RB MCU (running `TPT_SCPI_Server` firmware)
3. Execute the pulse train on the gate driver outputs (PB10/PB4)

## 2. Usage Workflow

1. **Connect Hardware**: Ensure Nucleo is connected via USB and flashed with correct firmware.
2. **Run Script**:
   ```bash
   python tests/test_tpt_pulse_train.py
   ```
3. **Define Pulses**: Select **Option [1]** to enter pulses manually (e.g., `10e-6`, `20e-6`, `done`).
4. **Load to MCU**: Confirm with `y`.
5. **Run**: Select **Option [3]** to fire the pulses.
6. **Reuse (New Feature)**: To run again with different settings or just re-load:
   - Select **Option [1]** again.
   - You will be asked: `Keep existing pulse train? [Y/n]`
   - Press **Enter** to keep your previous data.

## 3. Troubleshooting & Known Issues

### Issue: "Pulse Train Amnesia" (Fixed 2026-02-11)
**Symptoms:**
- Script would run successfully once.
- On the second run (without restarting script), usage of Option [1] would crash or error out.
- The script did not remember the previously entered pulse train.

**Root Cause:**
1. **Serial Buffer Corruption**: `run_pulses` (Option 3) sends a command but doesn't wait for a response. The MCU might send debug limits or other data. The *next* command (sent by `add_pulse` validation) would read this stale data instead of its expected response, causing a crash.
2. **Scope of Variable**: The `pulses` list was defined inside the loop, resetting on every iteration.

**Fix Implemented:**
- **Persistence**: `pulses` variable moved to outer scope to persist across loop iterations.
- **Buffer Flushing**: Added `board.flush_buffer()` in `ST.py` and called it after every run to clear stale data.
- **Optimized Driver**: Removed per-pulse SCPI validation queries in `ST.py` (`add_pulse`) to reduce traffic and potential for desynchronization.

## 4. Hardware Setup
- **PB10**: Positive Pulse (High-side)
- **PB4**: Negative Pulse (Low-side)
- **PA3/PA4**: USART3 (SCPI Control)

---
*If you encounter serial errors, ensure no other terminal (like TeraTerm or Screen) is holding the COM port.*
