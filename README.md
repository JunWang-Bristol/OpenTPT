# 🧲 Open Triple Pulse Test (OpenTPT)

[![License](https://img.shields.io/badge/License-BSD%204--Clause-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://www.python.org/)

> Open-source measurement system for magnetic core loss and inductance characterization.

**📄 Paper:** [Triple Pulse Test (TPT) for Characterizing Magnetic Components](https://research-information.bris.ac.uk/en/publications/triple-pulse-test-tpt-for-characterizing-power-loss-in-magnetic-c)

---

## 📋 Overview

The **Triple Pulse Test (TPT)** is a discontinuous excitation method for characterizing power losses and inductance in magnetic components. Unlike traditional continuous excitation methods, TPT uses a series of precisely timed pulses to achieve steady-state magnetic conditions rapidly.

### Discontinuous Procedure

| Pulse | Purpose | Description |
|-------|---------|-------------|
| **First Pulse** | Establish DC bias | No additional DC bias source needed |
| **Second Pulse(s)** | Stabilizing | Allow transients to settle |
| **Third Pulse** | Target cycle | Steady-state measurement |

<p align="center">
<img src="https://github.com/user-attachments/assets/79b16b9c-3685-4744-a00b-602cb5cbe33c" width="400">
<img src="https://github.com/user-attachments/assets/a5aeb696-d521-4b35-ae21-d3f0c416b4ee" width="400">
</p>

---

## ✨ Features

- ⚡ **Rapid Testing** – Short transition time (100–500 µs), ideal for end-of-line and 100% testing
- 🔄 **Bidirectional Current Flow** – Emulates practical B-H loop in PWM converters
- 💰 **Low Cost** – Reduced setup requirements compared to traditional methods
- 🌡️ **Constant Temperature** – Negligible heat generated during testing
- 📊 **DC Bias Capability** – Characterize saturation curves with built-in DC bias support
- 🖥️ **Web Dashboard** – Real-time visualization with Dash frontend

---

## 🔧 Hardware Setup

### Testing Circuit (Half-Bridge)

<p align="center">
<img src="https://github.com/user-attachments/assets/98e0528d-d1ae-4c81-9cbd-6fb57e1a7119" width="700">
</p>

### Example Equipment

| Component | Supported Models | Description |
|-----------|-----------------|-------------|
| **Power Supply** | BK Precision 9129B | Dual-channel supply (V+ and V-) |
| **Oscilloscope** | PicoScope 2408B | Captures voltage/current waveforms |
| **Control Board** | NUCLEO-H503RB, ST2402 | Generates PWM pulses for H-bridge |
| **Current Probe** | 100 mV/A (recommended) | Measures inductor current, > 20 MHz |
| **Voltage Probes** | 10:1 passive probes | Input/output voltage measurement |

> 💡 **Use Your Existing Equipment!**
>
> TPT is designed to work with lab equipment you likely already have. The modular architecture uses a **`hardware_configuration.json`** file to specify your power supply, oscilloscope, and control board. Simply configure the JSON with your device names and COM ports—no need to purchase specific models listed above.
>
> Adding support for new hardware is straightforward: implement the interfaces in `power_supply.py`, `oscilloscope.py`, or `board.py`.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Hardware setup (power supply, oscilloscope, control board) connected to your PC

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/JunWang-Bristol/TPT-Bristol.git
   cd TPT-Bristol
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/macOS
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure hardware** – Copy and edit the hardware configuration:
   ```bash
   cp hardware_configuration_template.json hardware_configuration.json
   ```
   
   Edit `hardware_configuration.json` with your port assignments:
   ```json
   {
       "power_supply": "BK9129B",
       "power_supply_port": "COM3",
       "oscilloscope": "PicoScope2408B",
       "oscilloscope_port": "COM5",
       "board": "NUCLEO-H503RB",
       "board_port": "COM6",
       "input_voltage_probe_scale": 10,
       "output_voltage_probe_scale": 10,
       "current_probe_scale": 0.1
   }
   ```

5. **Verify your setup** – Run tests to ensure everything is configured correctly:
   ```bash
   cd tests
   python -m pytest .
   ```
   
   Or run individual hardware tests:
   ```bash
   python board_tests.py
   python oscilloscope_tests.py
   python power_supply_tests.py
   ```

### Running Your First Measurement

#### Using Python API

```python
from src.tpt import InductanceMeasurement, CoreLossesMeasurement

# Initialize the measurement system
meas = InductanceMeasurement(
    power_supply='BK9129B',
    oscilloscope='PicoScope2408B',
    board='NUCLEO-H503RB',
    power_supply_port='COM3',
    oscilloscope_port='USB',
    board_port='COM6',
    current_probe_scale=0.1  # 100 mV/A probe
)

# Demagnetize the core before measurement
meas.demagnetize()

# Create test parameters for frequency sweep
params = meas.create_balanced_pulse_train(
    voltage=10,       # Voltage amplitude (V)
    frequency=100000, # Frequency (Hz)
    num_pulses=4      # Number of pulse pairs
)

# Run measurement...
# (See examples in documentation)

# Clean up after measurement
meas.demagnetize()
```

#### Using Web Dashboard

1. Navigate to the frontend directory:
   ```bash
   cd src/frontend
   ```

2. Run the dashboard:
   ```bash
   python frontend.py
   ```

3. Open your browser to `http://127.0.0.1:8050`

---

## 📁 Project Structure

```
TPT-Bristol/
├── src/
│   ├── tpt.py                 # Main measurement classes (InductanceMeasurement, CoreLossesMeasurement)
│   ├── post_processor.py      # Waveform analysis and loop extraction
│   ├── board.py               # Control board interface
│   ├── oscilloscope.py        # Oscilloscope interface
│   ├── power_supply.py        # Power supply interface
│   ├── boards/                # Board drivers
│   │   ├── NUCLEO-H503RB/     # STM32 NUCLEO board firmware
│   │   └── ST2402/            # ST2402 driver board support
│   ├── oscilloscopes/         # Oscilloscope drivers
│   │   └── PicoScope.py       # PicoScope 2408B driver
│   ├── power_supplies/        # Power supply drivers
│   │   └── BK.py              # BK Precision 9129B driver
│   └── frontend/              # Web dashboard
│       └── frontend.py        # Dash-based GUI
├── tests/                     # Unit tests
├── hardware_configuration_template.json
├── requirements.txt
└── LICENSE
```

---

## 📝 Configuration Notes

### Current Probe Scale

> ⚠️ **Important:** The `current_probe_scale` defines how to convert oscilloscope voltage readings to actual current values:
>
> `Current (A) = Oscilloscope Voltage (V) × probe_scale`

| Probe Sensitivity | Probe Scale Value |
|-------------------|-------------------|
| 100 mV/A | `0.1` |
| 1 V/A | `1.0` |
| 10 mV/A | `0.01` |

**Common mistake:** For a 100 mV/A probe, use `scale=0.1` (not 10). The probe outputs 100 mV when 1 A flows, so you multiply by 0.1 to get amperes.

---

## 🤝 Contributors

| Organization | Contributors |
|-------------|--------------|
| **PSMA/Würth Elektronik** | George Slama, Alfonso Martinez, Matt Wilkowski |
| **University of Bristol** | Jun Wang, Binyu Cui, Jingrong Yang |
| **University of Manchester** | Cheng Zhang |

<p align="center">
<img src="https://github.com/user-attachments/assets/c0c6bbed-de37-4ced-bac2-5fd5047c79f3" width="400">
</p>

---

## 📅 Roadmap

**🚧 Open TPT – Project Under Construction**

Expected release: **APEC 2026**

---

## 📄 License

This project is licensed under the **BSD 4-Clause License** – see the [LICENSE](LICENSE) file for details.

Copyright © 2023, University of Bristol

---

## 📚 Citation

If you use this project in your research, please cite:

```bibtex
@inproceedings{OpenTPT,
  title={Triple Pulse Test (TPT) for characterizing power loss in magnetic components in analogous to Double Pulse Test (DPT) for power electronics devices},
  author={Wang, Jun and others},
  booktitle={IEEE Proc. Annual Conference of the IEEE Industrial Electronics Society (IECON)},
  year={2020}
}
```

---

## 📧 Contact

For questions, issues, or contributions, please:
- Open an [issue](https://github.com/JunWang-Bristol/TPT-Bristol/issues) on GitHub
- Contact the team at jun.wang@bristol.ac.uk

