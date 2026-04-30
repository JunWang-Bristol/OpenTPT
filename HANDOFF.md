# Handoff: APEC Core Loss Measurement Debug

## Current State

We are debugging core loss measurement for a T26 3C90 toroid with 10 turns on the APEC branch. The measurement script runs but returns physically impossible results (B_peak=1.8mT, P_core=0mW). Current readings are essentially zero despite current probe being clamped.

## Hardware Setup

- **Board**: ST2402 half-bridge test fixture + NUCLEO-H503RB
- **PSU**: BK9129B (COM5) — using CH1 for +V, CH2 for -V (bipolar)
- **Scope**: PicoScope2408B (USB, ignores port config)
- **Board**: NUCLEO-H503RB v0.1.0 (COM4)
- **DUT**: T26 3C90 toroid, 10 turns primary, 1 turn secondary
- **Probes**:
  - V_pri: 10:1 voltage probe on CH A (scope channel 0)
  - V_sec: 10:1 voltage probe on CH B (scope channel 1)  
  - Current: Clamp-on probe 10mA/mV (100mV/A = 0.1 V/A) on CH C (scope channel 2)
- **User claims**: Current probe is clamped on correct wire, probe powered on

## Key Findings

### 1. Current Channel is Completely Dead
- **Max current reading**: 79 µA (just noise)
- **PSU confirms current flows**: 1.36 mA at 2V DC, 2.4 mA at 5V DC
- **Conclusion**: Current probe or scope channel C is not working physically
- **Likely causes**: Dead battery in clamp probe, probe not fully closed, wrong wire, scope Ch C broken

### 2. Pulse Timing is Suspicious
- **Firmware on APEC branch**: Uses DWT cycle counter for delays, HAL/LL GPIO
- **Waveform captures show unexpected patterns**:
  - 8-pulse capture: V_pri negative for 124 µs with brief 0.1 µs positive spikes
  - Single pulse capture: Output stays high for entire 500 µs acquisition
  - This does NOT match expected 10 µs pulses
- **Possible causes**:
  - DWT timer not working correctly on H503
  - `SystemCoreClock` variable incorrect
  - GPIO pins not actually switching
  - Scope triggering on wrong event

### 3. open-tpt Branch Has Better Firmware
- **Major improvements** over APEC branch firmware:
  - Bare-metal (no HAL/LL), direct register writes
  - Pre-computed DWT cycle counts (no 64-bit math at runtime)
  - Pre-computed BSRR values (atomic pin switching, no branches)
  - Configurable deadtime via `CONF:DEAD <seconds>`
  - Default minimum period: 10 ns (vs 500 ns on APEC)
  - Overhead compensation subtracts loop overhead from delays
- **The open-tpt firmware is significantly better** and should be used

### 4. Probe Scale Convention May Be Wrong
- `hardware_configuration.json`: `current_probe_scale = 0.1`
- In `PicoScope.py` `read_data()`: `data_in_volts *= probe_scale`
- For 100mV/A probe: to get Amps from volts, need `I = V / 0.1 = V × 10`
- Code multiplies by 0.1, so displayed current is actual × 0.01
- **Fix**: `current_probe_scale` should be **10**, not 0.1
- However, this does NOT explain zero current — just wrong scaling

### 5. PSU Uses Bipolar Configuration
- `tpt.py` sets both CH1 and CH2 to same voltage
- CH1 V+ → board V+, CH1 V- → board GND
- CH2 V+ → board GND, CH2 V- → board V-
- This creates ±V supply

## Tests Performed

| Test | Result |
|------|--------|
| `debug_core_loss.py` | Runs, captures waveform, current = 0, extraction fails |
| `check_current_probe.py` | Current channel reads noise only, no change with PSU on/off |
| `check_psu_current.py` | PSU shows 1.36mA at 2V → circuit is NOT open |
| `verify_pulse.py` | Single pulse stays high for 500µs (wrong!) |
| `check_psu_pulse.py` | With PSU off: V_pri = 10.3V sustained; with PSU on: same |
| `analyze_waveform2.py` | 8-pulse waveform: 124µs negative, 0.21µs positive |

## Critical Issues to Fix

### Priority 1: Flash open-tpt Firmware
- The APEC branch firmware may have timing bugs
- **open-tpt branch has bare-metal, optimized firmware**
- Need to build and flash it to Nucleo
- **Problem**: No ARM toolchain installed on this machine
- **Makefile location**: `src/boards/NUCLEO-H503RB/firmware/Makefile`
- **Makefile expects**: `arm-none-eabi-gcc` at STM32CubeIDE path or on PATH

### Priority 2: Fix Current Probe
- Even with perfect pulses, current channel shows nothing
- **Action needed**: Check current probe battery, verify clamp is fully closed, try different wire position
- Alternative: Use differential probe across TP6/TP7 (1Ω shunt) instead of clamp-on probe
- If using shunt: `current_probe_scale` should be 1.0 (1V/A) and connect to CH C

### Priority 3: Fix Probe Scale
- In `hardware_configuration.json`: change `current_probe_scale` from 0.1 to **10**
- For clamp-on probe: 100mV/A → scale factor = 10
- For shunt probe: 1V/A → scale factor = 1

### Priority 4: Verify Physical Setup
- User mentioned "TP16/TP18" but board only has TP1-TP11
- J16/J18 are DUT screw terminals (not test points)
- Voltage probe should be on J19 (BNC) for DUT voltage
- Current probe should be on wire between half-bridge and DUT
- Or use differential probe on TP6/TP7 for current

## Next Steps for Next Agent

1. **Install ARM toolchain** (if you want to rebuild firmware):
   - Option A: Download from https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads
   - Option B: Install STM32CubeIDE (includes toolchain)
   - Option C: Use `choco install gcc-arm-embedded` (may need admin)

2. **Build open-tpt firmware**:
   ```bash
   cd src/boards/NUCLEO-H503RB/firmware
   # Edit Makefile to set GCC_PATH if needed
   make
   ```

3. **Flash firmware** to Nucleo:
   - Nucleo appears as USB mass storage when plugged in
   - Copy `build/TPT_SCPI_Server.bin` to the Nucleo drive
   - Or use ST-Link Utility / STM32CubeProgrammer

4. **Fix current probe issue**:
   - Ask user to verify probe battery LED is on
   - Try clamping on different wire (high-side vs low-side vs return)
   - Verify probe is closed completely (click sound)
   - Alternative: Use BNC cable + differential probe on TP6/TP7

5. **Fix probe scale in software**:
   - Edit `hardware_configuration.json`: `"current_probe_scale": 10`

6. **Re-run measurement**:
   ```bash
   venv\Scripts\python.exe debug_core_loss.py
   ```
   - Should see non-zero current
   - Should see clean square wave on V_pri
   - Core loss extraction should succeed

## Files Modified on APEC Branch

- `src/tpt.py` — Changed trigger from CH_CURRENT to CH_VOLTAGE in `_configure_scope()`
- Added diagnostic scripts (untracked):
  - `debug_core_loss.py`
  - `check_current_probe.py`
  - `check_psu_current.py`
  - `verify_pulse.py`
  - `check_psu_pulse.py`
  - `analyze_waveform.py`
  - `analyze_waveform2.py`

## Git Status

- Branch: `APEC`
- Ahead of origin by 4 commits
- Uncommitted changes in `src/tpt.py`
- Untracked diagnostic scripts

## Important Notes

- **venv location**: `C:\Users\Alfonso\OpenTPT\venv`
- **Always use venv Python**: `venv\Scripts\python.exe`
- **PicoScope PATH fix**: `$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")`
- **PSU channels**: CH1=positive rail, CH2=negative rail (both set to same voltage)
- **Board minimum pulse**: 500 ns on APEC firmware, 10 ns on open-tpt firmware

## Reference Calculations

- T26 3C90, 10 turns: L ≈ 238 µH (ungapped)
- At 10V, 50kHz, 10µs pulse: ΔI = V·Δt/L = 10 × 10µs / 238µH ≈ **0.42 A**
- With 100mV/A probe: scope sees **42 mV** — should be easily visible
- If current is actually 6.8mA (due to high resistance): scope sees 0.68mV — still visible on ±100mV range

## Questions for User

1. Is the current probe battery LED on? If not, replace battery.
2. Are you measuring voltage at J19 (BNC) or somewhere else?
3. Is the DUT actually connected between FIX_A and FIX_B screw terminals?
4. Do you hear a click when closing the current probe clamp?
5. Are you using the latest open-tpt firmware or the older APEC firmware?
