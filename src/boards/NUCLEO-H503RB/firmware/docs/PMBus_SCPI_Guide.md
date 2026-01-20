# PMBus SCPI Commands Guide

This guide explains how to control the CoolX600 power supply via PMBus using SCPI commands sent to the NUCLEO-H503RB board.

## Hardware Setup

### Connections
| NUCLEO-H503RB | CoolX600 PMBus |
|---------------|----------------|
| PB10 (D6)     | SCL            |
| PB11 (D5)     | SDA            |
| GND           | GND            |

> **Note:** External pull-up resistors (4.7kΩ) are required on SDA and SCL lines.

### Default PMBus Address
The CoolX600 CMD-W0 default address is `0x5A` (90 decimal).

---

## SCPI Commands Reference

### Initialization

| Command | Description |
|---------|-------------|
| `PMBUS:INIT` | Initialize PMBus interface |
| `PMBUS:ADDR <address>` | Set PMBus slave address (decimal) |
| `PMBUS:ADDR?` | Query current PMBus address |

**Example:**
```
PMBUS:INIT
PMBUS:ADDR 90
```

### Page Selection

| Command | Description |
|---------|-------------|
| `PMBUS:PAGE <page>` | Select output page (0-7) |
| `PMBUS:PAGE?` | Query current page |

### Power Control

| Command | Description |
|---------|-------------|
| `OUTP ON` | Turn output ON |
| `OUTP OFF` | Turn output OFF |
| `OUTP:OPER <value>` | Set OPERATION register value |
| `OUTP:OPER?` | Query OPERATION register |
| `OUTP:PROT:CLE` | Clear all fault flags |

### Voltage Control

| Command | Description |
|---------|-------------|
| `SOUR:VOLT <voltage>` | Set output voltage (V) |
| `SOUR:VOLT?` | Query voltage setpoint |
| `VOLT <voltage>` | Set output voltage (V) |
| `VOLT?` | Query voltage setpoint |

**Example:**
```
SOUR:VOLT 12.0
```

### Measurements

| Command | Description |
|---------|-------------|
| `MEAS:VOLT?` | Measure output voltage (V) |
| `MEAS:CURR?` | Measure output current (A) |
| `MEAS:POW?` | Measure output power (W) |
| `MEAS:TEMP?` | Measure temperature (°C) |
| `MEAS:VOLT:IN?` | Measure input voltage (V) |
| `MEAS:CURR:IN?` | Measure input current (A) |

### Status

| Command | Description |
|---------|-------------|
| `STAT:BYTE?` | Query STATUS_BYTE register |
| `STAT:WORD?` | Query STATUS_WORD register |

### Device Information

| Command | Description |
|---------|-------------|
| `SYST:MFR:ID?` | Query manufacturer ID |
| `SYST:MFR:MOD?` | Query model name |
| `SYST:MFR:SER?` | Query serial number |

### Raw Register Access

| Command | Description |
|---------|-------------|
| `PMBUS:REG <cmd>,<data>` | Write byte/word to PMBus register |
| `PMBUS:REG? <cmd>,<size>` | Read from PMBus register (size: 1 or 2 bytes) |

**Example:**
```
PMBUS:REG? 0x8B,2    ; Read VOUT (2 bytes)
PMBUS:REG 0x01,0x80  ; Write to OPERATION register
```

---

## Usage Examples

### Basic Power Supply Control
```
; Initialize and configure
PMBUS:INIT
PMBUS:ADDR 90

; Set voltage to 12V and turn on
SOUR:VOLT 12.0
OUTP ON

; Read measurements
MEAS:VOLT?
MEAS:CURR?
MEAS:POW?

; Turn off
OUTP OFF
```

### Multi-Output Control (if applicable)
```
; Select page 0 (first output)
PMBUS:PAGE 0
SOUR:VOLT 5.0
OUTP ON

; Select page 1 (second output)  
PMBUS:PAGE 1
SOUR:VOLT 3.3
OUTP ON
```

### Fault Handling
```
; Check for faults
STAT:WORD?

; Clear faults
OUTP:PROT:CLE
```

---

## Error Handling

If a PMBus communication error occurs, the SCPI error queue will contain an execution error. Use `SYST:ERR?` to retrieve error details.

Common issues:
- **No response:** Check I2C connections and pull-up resistors
- **NACK:** Verify PMBus address is correct
- **Wrong values:** Ensure correct page is selected

---

## PMBus Command Codes Reference

| Register | Code | Type |
|----------|------|------|
| PAGE | 0x00 | R/W Byte |
| OPERATION | 0x01 | R/W Byte |
| CLEAR_FAULTS | 0x03 | Send Byte |
| VOUT_MODE | 0x20 | Read Byte |
| VOUT_COMMAND | 0x21 | R/W Word |
| STATUS_BYTE | 0x78 | Read Byte |
| STATUS_WORD | 0x79 | Read Word |
| READ_VIN | 0x88 | Read Word |
| READ_IIN | 0x89 | Read Word |
| READ_VOUT | 0x8B | Read Word |
| READ_IOUT | 0x8C | Read Word |
| READ_TEMP1 | 0x8D | Read Word |
| READ_POUT | 0x96 | Read Word |
| MFR_ID | 0x99 | Block Read |
| MFR_MODEL | 0x9A | Block Read |
| MFR_SERIAL | 0x9E | Block Read |
