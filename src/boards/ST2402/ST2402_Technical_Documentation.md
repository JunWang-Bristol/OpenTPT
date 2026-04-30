# ST2402 – Triple Pulse Core Tester User Manual

**Document revision:** 3  
**Hardware basis:** current ST2402 design set (updated board files)  
**Designed by:** CoreDataX / OpenTPT project

---

## 1. Purpose

The **ST2402** is a half-bridge test board used with OpenTPT to run triple-pulse style experiments on magnetic components and related power-stage setups. It is intended for controlled lab use with an external DC supply, oscilloscope, and an ST Nucleo-H503RB controller board.

In practical terms, ST2402 provides:

- A power half-bridge stage for pulse excitation.
- Isolated gate-drive paths for robust switching control.
- Dedicated connection points for DUT wiring and measurements.
- Flexible fixture/probe interfaces (BNC, headers, banana points, and test points).

---

## 2. Conceptual Design (How the Board Works)

At system level, ST2402 is organized into three conceptual blocks:

1. **Control block (Nucleo headers `J1`, `J2`)**  
   Receives timing/control from the Nucleo-H503RB and routes signals into the drive stage.

2. **Drive and power block**  
   - Two MOSFETs (`Q1`, `Q2`) form the switching half-bridge.  
   - Two isolated gate drivers (`U6`, `U8`) drive the switches.  
   - Isolated DC/DC modules (`U1`, `U7`) power the isolated driver domains.  
   - Input-side protection includes `F1` and `F2` (6.3A fast-acting fuse path).

3. **Fixture and measurement block**  
   Provides DUT interface and measurement breakout through BNC connectors (`J13`, `J19`), fixture headers (`J11`, `J12`, `J21`, `J22`), and test/probe points (`J14`, `J18`, `TP*`).

---

## 3. Connector Quick-Reference (Wiring Order + Probe Hookup)

Use this sequence for bring-up to reduce setup errors.

| Order | Connector(s) | What to connect | Why / Notes |
|------:|--------------|-----------------|-------------|
| 1 | `J1`, `J2` | Install Nucleo-H503RB | Required control interface before running pulses |
| 2 | Nucleo USB | Connect to host PC | Powers control side and enables OpenTPT communication |
| 3 | `J9` | Connect DC supply input | Main board power input for the switching stage |
| 4 | `J15`, `J16`, `J17` and/or fixture headers `J11`/`J12`/`J21`/`J22` | Connect DUT / fixture loop | Use the connection style that matches your fixture and current level |
| 5 | `J13` (BNC) | Voltage probe channel (scope CH1 recommended) | Primary voltage measurement point on fixture interface |
| 6 | `J19` (BNC) | Current-related probe channel (scope CH2 recommended) | Measurement channel for current loop/return-related observation |
| 7 | `TP13`, `TP14`, `TP15`, `TP1`, `TP2`, `TP16`-`TP19` | Optional debug probes | Use for extra node visibility during tuning/debug |

> Recommended practice: keep one consistent scope channel mapping (for example CH1=voltage at `J13`, CH2=current-related at `J19`) across all test scripts and saved datasets.

---

## 4. Step-by-Step Setup Procedure

1. **Mechanical check**  
   Confirm board is mounted securely (holes `H1`-`H8`) and no conductive debris is present.

2. **Controller installation**  
   Fit the Nucleo-H503RB onto `J1`/`J2`; connect USB to host.

3. **Power wiring**  
   With supply output OFF, wire 12V DC input to `J9`.

4. **DUT wiring**  
   Connect the DUT loop using the selected fixture interface (`J15`/`J16`/`J17` or `J11`/`J12`/`J21`/`J22`).

5. **Instrumentation hookup**  
   - Scope CH1 to `J13` BNC.  
   - Scope CH2 to `J19` BNC.  
   - Add auxiliary probes at `TP*` only if needed.

6. **Power-up sequence**  
   Turn on control side first (USB/Nucleo), then enable DC supply output.

7. **Run test from OpenTPT**  
   Start with conservative pulse settings and increase stress gradually.

8. **Power-down sequence**  
   Disable DC supply output first, then remove/adjust DUT wiring.

---

## 5. Pre-Test Checklist

Complete this checklist before enabling pulses:

| Check | Item | Pass Criteria |
|------:|------|---------------|
| ☐ | Mechanical integrity | Board is firmly mounted; no loose hardware; no conductive debris |
| ☐ | Nucleo installation | Nucleo-H503RB seated correctly on `J1`/`J2`; USB link active |
| ☐ | Input wiring | DC input polarity and terminal tightness at `J9` verified |
| ☐ | DUT loop wiring | DUT connected to intended fixture points; no accidental shorts |
| ☐ | Scope channels | CH1 on `J13`, CH2 on `J19`, probe attenuation and bandwidth settings confirmed |
| ☐ | Optional debug probes | Extra probes on `TP*` do not short adjacent nodes or ground unintended nets |
| ☐ | Fuse condition | `F1` and `F2` are present and visually/electrically healthy |
| ☐ | Supply limits | Supply voltage/current limits set to conservative startup values |
| ☐ | Software readiness | OpenTPT target configuration and pulse profile reviewed before run |

> Operator sign-off suggestion: record date, board ID, DUT ID, and scope channel map in the run log before each test.

---

## 6. Safety and Good Lab Practice

- Treat the board as a live power-electronics assembly during operation.
- Never rewire DUT or probes while supply output is enabled.
- Verify fuse condition (`F1`, `F2`) before repeated high-energy tests.
- Keep wiring short and low-inductance, especially in high-current loops.
- Start at low voltage/current and ramp only after waveform validation.

---

## 7. Practical Usage Notes

- Keep measurement grounding/probe return strategy consistent between runs.
- If waveforms are noisy, improve lead routing before changing firmware settings.
- Record connector/probe mapping with each dataset to maintain traceability.
- Use the same fixture connector set for a full campaign to avoid wiring drift.

---

## 8. Hardware Reference Summary

### 8.1 Main power/control devices

| Ref | Device |
|-----|--------|
| `Q1`, `Q2` | STB100N10F7 |
| `U6`, `U8` | Si8271DB |
| `U1`, `U7` | R1S-1212 |
| `U2` | LM317L_SOT-89 |
| `F1`, `F2` | 6.3A fast-acting fuse path |

### 8.2 Board construction

- 2-layer PCB (`F.Cu`, `B.Cu`)
- 1.6 mm board thickness
- 8 mounting holes (`H1`-`H8`, M3 class)

---

## 9. Manufacturing Outputs

Manufacturing data is available in:

- `r1 Gerbers/`
- `r2 Gerbers/`
- `r3 Gerbers/`

Use the latest validated set in your release process.

---

*Last updated: 2026-02-17 (manual-style update for revised ST2402 board files)*
