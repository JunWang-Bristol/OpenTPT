# ST2402 – Triple Pulse Core Tester PCB

**Revision:** 1  
**Date:** 2025-01-31  
**Designed by:** OpenTPT project  
**Part of:** [Open Triple Pulse Test (OpenTPT)](../../README.md)

---

## 1. Overview

The **ST2402** is a custom PCB designed for the **Triple Pulse Test (TPT)** method of characterizing power losses and inductance in magnetic components. It implements a **half-bridge power stage** with integrated gate driving, current sensing, and fixture connections — controlled by an **ST Nucleo-H503RB** development board mounted directly on the PCB.

### Key Capabilities

| Feature | Specification |
|---------|---------------|
| **Topology** | Half-bridge (high-side + low-side MOSFET) |
| **Max Input Voltage (Vcc)** | +-30 V |
| **Gate Driver IC** | TI UCC21520 (isolated, dual-channel) |
| **Microcontroller** | ST Nucleo-H503RB (plugs into on-board headers) |
| **Fuse Protection** | 6.3 A Fast-Acting (TR5 fuse holders) |
| **PCB Layers** | 2-layer (Front copper + Back copper) |
| **Board Thickness** | 1.6 mm |
| **Mounting** | 8× M3 mounting holes (DIN965) |

---

## 2. Functional Block Diagram

```
                    ┌─────────────────────────────────────────────────┐
                    │                  ST2402 PCB                      │
                    │                                                  │
  ┌──────────┐      │   ┌─────────┐    ┌───────────┐    ┌──────────┐  │
  │  Nucleo  │──PWM─┼──►│  Gate   │───►│Half-Bridge│───►│ Fixture  │──┼──► DUT
  │ H503RB   │──SD──┼──►│ Driver  │    │  (FETs)   │    │Connectors│  │   (Magnetic
  │          │◄─5V──┼───│UCC21520 │    │           │    │BNC/Screw │  │    Core)
  └──────────┘      │   └─────────┘    └─────┬─────┘    └──────────┘  │
                    │                        │                         │
                    │              ┌─────────▼─────────┐               │
                    │              │  Current Sense     │               │
                    │              │  (Shunt Resistors) │               │
                    │              └───────────────────┘               │
                    │                                                  │
  ┌──────────┐      │   ┌──────────────┐                               │
  │ DC Power │──V+──┼──►│ Fuses (F1,F2)│──► Half-Bridge                │
  │ Supply   │──GND─┼──►│ 6.3A FA      │                               │
  └──────────┘      │   └──────────────┘                               │
                    └─────────────────────────────────────────────────┘
```

---

## 3. Schematic Sheets

The design is organized into **4 hierarchical schematic sheets**:

| Sheet | File | Description |
|-------|------|-------------|
| **Root** | `ST2402.kicad_sch` | MCU connector headers (Nucleo interface), mounting holes, global signal routing |
| **Driver** | `driver.kicad_sch` | UCC21520 gate driver, MOSFET half-bridge, power input with fuse protection, decoupling |
| **Fixture** | `fixture.kicad_sch` | DUT (Device Under Test) connections — BNC/SMA coaxial connectors, screw terminals |
| **Current Sense** | `currentsense.kicad_sch` | Shunt resistor network for current measurement (1Ω, 0805 SMD) |

---

## 4. Connector Pinout & Wiring Guide

### 4.1 Nucleo MCU Headers (J1, J2 — 2×19 Pin Headers)

The ST Nucleo-H503RB plugs directly into two 2×19 Morpho-compatible pin headers on the PCB. The following signals are actively routed:

| Signal | Nucleo Pin | Direction | Description |
|--------|-----------|-----------|-------------|
| **PWM** | D5/D6 area | MCU → Driver | PWM gate drive signal to UCC21520 |
| **SD** | Digital I/O | MCU → Driver | Shutdown / enable signal for gate driver |
| **5V** | 5V rail | MCU → Board | 5V supply from Nucleo USB to gate driver |
| **GND** | GND | Common | Common ground reference |
| **AREF** | AREF | MCU | Analog reference (exposed on header) |
| **VIN** | VIN | Power | External voltage input to Nucleo |

> **⚠️ Important:** The Nucleo board provides 5V power to the gate driver circuit via the USB connection. Ensure the Nucleo is powered before applying the DC bus voltage.

### 4.2 Additional MCU Headers

| Connector | Type | Pins | Footprint | Purpose |
|-----------|------|------|-----------|---------|
| **J3** | 1×6 Pin Header | 6 | 2.54mm vertical | Auxiliary I/O |
| **J4** | 1×8 Pin Header | 8 | 2.54mm vertical | Nucleo CN7 side signals (5V, GND, VIN, analog) |
| **J5** | 1×6 Pin Header | 6 | 2.54mm vertical | Auxiliary I/O |
| **J6** | 1×10 Pin Header | 10 | 2.54mm vertical | Nucleo CN10 side signals (D2–D12, PWM, TX, RX) |

### 4.3 Power Input Terminals (Driver Sheet)

| Connector | Type | Signal | Description |
|-----------|------|--------|-------------|
| **J9** | Screw Terminal (1×2) | **V+** / **Com** | DC bus positive and common/midpoint |
| **J10** | Screw Terminal (1×1) | **Gnd** | Power ground connection |
| **J11** | Screw Terminal (1×1) | Power | Additional power connection |

**Wiring:**
1. Connect your **DC power supply positive** terminal to the **V+** screw terminal
2. Connect the **power supply negative** terminal to the **Gnd** screw terminal
3. The **Com** terminal is the half-bridge midpoint / output node

> **⚠️ Maximum voltage: 20V DC.** Exceeding this may damage the gate driver and MOSFETs.

### 4.4 Fixture / DUT Connections (Fixture Sheet)

| Connector | Type | Signal | Description |
|-----------|------|--------|-------------|
| **J19** | BNC Coaxial | Voltage sense | Connect oscilloscope voltage probe here |
| **J12, J15, J16, J18** | Screw Terminal (1×1) | DUT terminals | Connect magnetic core / inductor under test |
| **J13** | 2×2 Connector | Fixture harness | 4-pin fixture connection |
| **J14** | 2×3 Connector | Fixture harness | 6-pin fixture connection |

**DUT Connection:**
- **FIX_A** — One side of the Device Under Test
- **FIX_B** — Other side of the Device Under Test  

Connect your magnetic component (inductor / transformer winding) between the FIX_A and FIX_B terminals.

### 4.5 Auxiliary Connectors

| Connector | Type | Purpose |
|-----------|------|---------|
| **J7** | 1×2 Pin Header | General-purpose I/O |
| **J8** | 1×2 Pin Header | General-purpose I/O |

---

## 5. Test Points

Test points are provided for probing and debugging. All test points use **2.0mm THT pads** (1.0mm drill).

### Root Sheet Test Points

| Test Point | Net / Signal | Purpose |
|-----------|-------------|---------|
| **TP1** | PWM related | PWM signal monitoring |
| **TP2** | PWM related | PWM signal monitoring |
| **TP3** | Signal | Signal monitoring |
| **TP4** | SD/PWM area | Shutdown or PWM signal probe point |
| **TP5** | Signal | Signal monitoring |

### Driver Sheet Test Points

| Test Point | Label | Net | Purpose |
|-----------|-------|-----|---------|
| **TP8** | — | Vcc rail | Verify gate driver supply voltage |
| **TP9** | WHT (White) | PWM input | Probe the PWM input to the gate driver |
| **TP10** | — | Gate drive | Gate output monitoring |
| **TP11** | BLK (Black) | Ground ref | Ground reference probe point |

### Current Sense Test Points

| Test Point | Purpose |
|-----------|---------|
| **TP6, TP7** | Current shunt voltage measurement — connect differential probe here |

---

## 6. Power Circuit Details

### 6.1 Half-Bridge Driver (UCC21520)

The **TI UCC21520** is a dual-channel isolated gate driver that drives the high-side and low-side MOSFETs of the half-bridge. Key features:

- **Isolated** high-side and low-side drive outputs
- **Programmable dead time** (via DT pin and external resistor)
- **Shutdown input** (SD) — active-low, directly controlled by the Nucleo MCU
- **PWM input** (IN) — receives the PWM signal from the Nucleo

### 6.2 Protection

| Component | Value | Purpose |
|-----------|-------|---------|
| **F1** | 6.3A Fast-Acting (TR5 fuse holder) | Protects high-side power path |
| **F2** | 6.3A Fast-Acting (TR5 fuse holder) | Protects low-side power path |
| **D1, D2, D3** | Diodes | Flyback / freewheeling protection |

### 6.3 Decoupling & Filtering

| Component | Value | Package | Purpose |
|-----------|-------|---------|---------|
| **C1** | 33pF / 25V | 0805 SMD | PWM input filtering |
| **C5** | 220nF / 50V | 0805 SMD | Gate driver Vcc decoupling |
| **C6** | 33pF / 25V | 0805 SMD | Additional filtering |
| **C12** | 4.7µF | THT film (18×11mm, 15mm pitch) | DC bus bulk decoupling |

### 6.4 Gate Resistors

| Component | Value | Package | Purpose |
|-----------|-------|---------|---------|
| **R23** | 10Ω | 0805 SMD | Gate drive resistor (controls switching speed) |
| **R18** | 43kΩ | 0805 SMD | Dead-time programming resistor |

---

## 7. Current Sensing

The current sense sub-circuit uses a network of **shunt resistors** to measure the current flowing through the DUT.

| Component | Value | Package | Description |
|-----------|-------|---------|-------------|
| **R9** (and others) | 1Ω | 0805 SMD | Current sense shunt resistor |

**How it works:**
1. Current flows through the shunt resistor network
2. The voltage across the resistors is proportional to the current (V = I × R)
3. Connect a **differential voltage probe** or **oscilloscope** to **TP6/TP7** to measure the current
4. With a 1Ω shunt: **1V = 1A**

> **💡 Tip:** For high-current measurements, the shunt resistors may be paralleled to reduce effective resistance and power dissipation.

---

## 8. Assembly & Setup Guide

### 8.1 Before You Begin

**Required tools:**
- Soldering iron (for SMD and THT components)
- Hot air rework station (recommended for SMD)
- Multimeter
- Oscilloscope with probes

**Required materials:**
- Populated ST2402 PCB (or bare board + BOM components)
- ST Nucleo-H503RB development board
- DC power supply (≤20V)
- Magnetic component (DUT) to test
- BNC cables and oscilloscope probes

### 8.2 Assembly Steps

1. **Solder SMD components first** — resistors (0805), capacitors (0805), gate driver IC (UCC21520), MOSFETs, diodes
2. **Solder THT components** — pin headers, screw terminals, fuse holders, bulk capacitor (C12), BNC connector
3. **Install fuses** — Insert 6.3A fast-acting TR5 fuses into fuse holders F1 and F2
4. **Mount the board** — Use M3 screws through the 8 mounting holes (H1–H8)
5. **Plug in the Nucleo** — Align the Nucleo-H503RB with the 2×19 pin headers (J1, J2) and press down firmly

### 8.3 Initial Power-Up Checklist

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Connect Nucleo via USB | Power LED on Nucleo lights up |
| 2 | Measure 5V at TP8 | 5V ± 0.25V |
| 3 | Measure GND at TP11 | 0V (ground reference) |
| 4 | Check PWM at TP9 | No signal (PWM not yet started) |
| 5 | Apply DC bus voltage (start low, e.g., 5V) | Verify with multimeter at V+ terminal |
| 6 | Check fuse continuity | F1, F2 should be < 1Ω |

### 8.4 Connecting the DUT (Device Under Test)

1. **Power off** the DC supply
2. Connect one terminal of your magnetic component to **FIX_A**
3. Connect the other terminal to **FIX_B**
4. Ensure connections are firm (use screw terminals or fixture connectors)
5. Connect voltage probe to the **BNC connector (J19)**
6. Connect current probe to **TP6/TP7** (or use the on-board shunt)

---

## 9. Operating Procedure

### 9.1 Running a Triple Pulse Test

1. **Power the Nucleo** via USB cable
2. **Set DC supply voltage** (do not exceed 20V)
3. **Enable the DC supply output**
4. **Start the TPT measurement** from the OpenTPT software:
   - Via Python API: Use `InductanceMeasurement` or `CoreLossesMeasurement` class
   - Via Web Dashboard: Navigate to `http://127.0.0.1:8050`
5. The Nucleo will output PWM pulses to drive the half-bridge
6. The oscilloscope captures voltage and current waveforms
7. **Disable the DC supply** after measurement
8. **Demagnetize** the core using the software's demagnetize function

### 9.2 Safety Precautions

> **⚠️ WARNING: This board handles power electronics voltages and currents. Observe the following:**

- **Never exceed +- 30V DC** on the power input
- **Always power the Nucleo first** before applying bus voltage
- **Do not touch** the board while DC power is applied
- **Check fuse condition** before each test session
- **Ensure DUT is properly secured** before applying power
- **Keep the area clear** of conductive debris
- **Use appropriate probe ratings** for your voltage/current levels

---

## 10. Gerber Files

Manufacturing Gerber files are located in the `r1 Gerbers/` directory:

| File | Layer |
|------|-------|
| `ST2402-F_Cu.gbr` | Front copper |
| `ST2402-B_Cu.gbr` | Back copper |
| `ST2402-F_Mask.gbr` | Front solder mask |
| `ST2402-B_Mask.gbr` | Back solder mask |
| `ST2402-F_Silkscreen.gbr` | Front silkscreen |
| `ST2402-B_Silkscreen.gbr` | Back silkscreen |
| `ST2402-Edge_Cuts.gbr` | Board outline |
| `ST2402-PTH.drl` | Plated through-hole drill file |
| `ST2402-NPTH.drl` | Non-plated through-hole drill file |
| `ST2402-job.gbrjob` | Gerber job file |
| `ST2402r1.zip` | Complete Gerber package (ready to upload) |

**To order PCBs:** Upload `ST2402r1.zip` to your PCB manufacturer (e.g., JLCPCB, PCBWay, OSH Park). Specify:
- **Layers:** 2
- **Thickness:** 1.6mm
- **Surface Finish:** HASL or ENIG (recommended)
- **Copper Weight:** 1 oz (standard) or 2 oz (for higher current capability)

---

## 11. Bill of Materials (BOM)

A detailed BOM is provided in `ST2402 BOM.xlsx`. Key component categories:

| Category | Examples | Quantity |
|----------|----------|----------|
| Gate Driver IC | UCC21520 (U1) | 1 |
| MOSFETs | Power MOSFETs (Q1, etc.) | 2 |
| Fuse Holders | TR5 Littelfuse No.560 (F1, F2) | 2 |
| Fuses | 6.3A Fast-Acting TR5 | 2 |
| Resistors (0805 SMD) | Various values (1Ω–43kΩ) | ~20+ |
| Capacitors (0805 SMD) | 33pF, 220nF | ~10+ |
| Capacitors (THT Film) | 4.7µF (C12) | 1 |
| Diodes | Protection diodes (D1–D3) | 3 |
| Pin Headers (2×19) | Nucleo connectors (J1, J2) | 2 |
| Pin Headers (1×N) | Various (J3–J8) | 6 |
| Screw Terminals | Power input (J9–J12, etc.) | 4+ |
| BNC Connector | Voltage sense (J19) | 1 |
| Mounting Holes | M3 DIN965 (H1–H8) | 8 |
| Test Points | 2mm THT pad (TP1–TP11) | 11 |

---

## 12. Troubleshooting

| Symptom | Possible Cause | Solution |
|---------|---------------|----------|
| No PWM output | Nucleo not programmed | Flash the OpenTPT firmware to the Nucleo |
| No 5V at TP8 | Nucleo not powered / bad solder joint | Check USB connection; re-solder 5V header pins |
| Fuse blows immediately | Short circuit in DUT or wiring | Check DUT connections; inspect for solder bridges |
| Gate driver not switching | SD pin held low (shutdown active) | Verify SD signal from Nucleo; check pull-up resistor |
| Excessive ringing on waveform | Parasitic inductance in wiring | Shorten DUT leads; use twisted pair connections |
| Incorrect current reading | Wrong shunt value or probe setup | Verify R_shunt; check differential probe polarity |
| Board doesn't fit Nucleo | Wrong pin header height | Use standard 2.54mm pin headers; check alignment |

---

## 13. Design Files

All KiCAD source files are located in `src/boards/ST2402/`:

| File | Description |
|------|-------------|
| `ST2402.kicad_pro` | KiCAD project file |
| `ST2402.kicad_sch` | Root schematic (Nucleo interface) |
| `ST2402.kicad_pcb` | PCB layout |
| `driver.kicad_sch` | Driver sub-sheet (gate driver + half-bridge) |
| `fixture.kicad_sch` | Fixture sub-sheet (DUT connections) |
| `currentsense.kicad_sch` | Current sense sub-sheet |
| `ST2402 BOM.xlsx` | Bill of Materials |
| `r1 Gerbers/` | Manufacturing files |

**KiCAD Version:** 8.0

---

*Last updated: 2025-01-31 | Part of the [OpenTPT](https://github.com/JunWang-Bristol/OpenTPT) project*
