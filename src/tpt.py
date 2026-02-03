"""
TPT (Trapezoidal Pulse Testing) Module for Magnetic Component Characterization
===============================================================================

This module provides inductance and core loss measurement capabilities using
the Trapezoidal Pulse Testing method with an H-bridge driver circuit.

HARDWARE SETUP
--------------
The system consists of:
1. **Power Supply** (e.g., BK9129B): Dual-channel supply providing V+ (CH1) and V- (CH2)
2. **Oscilloscope** (e.g., PicoScope 2408B): Captures voltage and current waveforms
3. **Control Board** (e.g., NUCLEO-H503RB): Generates PWM pulses for H-bridge
4. **H-Bridge Driver** (e.g., ST2402): Applies alternating voltage pulses to DUT
5. **Current Probe**: Measures inductor current (e.g., 100 mV/A sensitivity)

CRITICAL: PROBE SCALE CONFIGURATION
-----------------------------------
The `current_probe_scale` parameter defines how to convert oscilloscope voltage
readings to actual current values:

    Current_in_Amps = Oscilloscope_Voltage × probe_scale

For a 100 mV/A current probe (outputs 100mV per Amp):
    - If scope reads 0.5V, actual current = 0.5 × 0.1 = 0.05A = 50mA
    - **probe_scale = 0.1** (NOT 10!)

For a 1 V/A current probe:
    - probe_scale = 1.0

Common mistake: Confusing "100 mV/A" as needing scale=10. The probe outputs
100mV when 1A flows, so you MULTIPLY by 0.1, not 10.


TPT METHOD OVERVIEW
-------------------
The Trapezoidal Pulse Testing method applies alternating voltage pulses to an
inductor and measures the resulting current slope:

    L = V × dt / dI

Where:
    - V is the applied voltage during the pulse
    - dt is the pulse duration (half-period)
    - dI is the change in current during that pulse


FLUX BALANCE AND DEMAGNETIZATION
--------------------------------
**Critical Insight**: The pulse train must have BALANCED VOLT-SECONDS to avoid
residual magnetization in the core.

Problem with standard pulse trains:
    - If the total pulse count creates an odd number of half-periods, or
    - If there's padding at the end after a positive pulse,
    - The core is left with residual flux (DC magnetization)

Solution:
    - Use `create_balanced_pulse_train()` for measurements requiring zero DC bias
    - Use `demagnetize()` after measurements to reset core flux to zero
    - Ensure pulse trains have even number of half-periods

Example:
    BAD:  [5us, 5us, 5us, 5us, 5us, 5us, 5us, 5us, 160us]  # 9 periods, ends positive
    GOOD: [5us, 5us, 5us, 5us, 5us, 5us, 5us, 5us]         # 8 periods, balanced


DC BIAS MEASUREMENT (TPT Method)
--------------------------------
To measure inductance with DC bias (for saturation characterization):

**Method 1: First Long Pulse (Traditional TPT)**
    - First pulse is extended to build up DC current
    - DC_current = V × t_long / L
    - Subsequent pulses measure L at that DC bias point

**Method 2: Asymmetric Voltage (Alternative)**
    - Use different V+ and V- to create net volt-seconds per cycle
    - V+ > V- creates positive DC current buildup over multiple cycles
    - Allows gradual DC bias buildup without large first pulse

Example for asymmetric voltage:
    V+ = 14V, V- = 6V at 50% duty cycle
    Net voltage per cycle = (14 - 6) / 2 = 4V average
    DC current builds up each cycle


HARDWARE TROUBLESHOOTING
------------------------
**Power Supply Channel Issues:**
    - If CH2 shows low voltage with high current, it's in current limiting
    - This indicates a short or excessive load on the H-bridge negative rail
    - Check MOSFET drivers and wiring on the H-bridge board
    
**Expected idle state:**
    - CH1: Set voltage, ~0 mA (no load when idle)
    - CH2: Set voltage, ~0 mA (no load when idle)
    
**Problem state (hardware fault):**
    - CH1: 10V, ~0 mA (OK)
    - CH2: Low voltage, high current (H-bridge drawing current when it shouldn't)


MEASUREMENT ACCURACY NOTES
--------------------------
- Bode100 reference: ~3.6 mH for RM10/N87/26T ungapped
- TPT measurements typically show ~2.5-3 mH at 100kHz
- Discrepancy sources:
    1. Frequency-dependent permeability (μr decreases with frequency)
    2. Winding resistance effects at high frequency
    3. Probe calibration accuracy
    4. Core temperature during measurement


USAGE EXAMPLES
--------------
Basic inductance measurement:
    >>> meas = InductanceMeasurement(
    ...     power_supply='BK9129B',
    ...     oscilloscope='PicoScope2408B',
    ...     board='NUCLEO-H503RB',
    ...     power_supply_port='COM4',
    ...     oscilloscope_port='USB',
    ...     board_port='COM3',
    ...     current_probe_scale=0.1  # 100 mV/A probe
    ... )
    >>> meas.demagnetize()  # Start with clean core
    >>> params = meas.create_balanced_pulse_train(voltage=10, frequency=100000, num_pulses=4)
    >>> # ... configure scope and run measurement ...
    >>> meas.demagnetize()  # Clean up after measurement

DC bias measurement:
    >>> params = meas.calculate_dc_bias_parameters(
    ...     voltage=10, frequency=100000, num_pulses=4, dc_bias_current=0.1
    ... )
    >>> # First pulse will be extended to reach 100mA DC bias


Authors: TPT-Bristol Team
Last Updated: January 2026
"""

from board import Board
from power_supply import PowerSupply
from oscilloscope import Oscilloscope
import matplotlib.pyplot as plt
import os
import json
import math
import copy
import time
import post_processor


class Measurement():

    def __init__(self, power_supply, oscilloscope, board, power_supply_port, oscilloscope_port, board_port, input_voltage_probe_scale=1, output_voltage_probe_scale=1, current_probe_scale=1):
        self.power_supply = self.instantiate_power_supply(power_supply, power_supply_port)
        self.oscilloscope = self.instantiate_oscilloscope(oscilloscope, oscilloscope_port)
        self.input_voltage_probe_scale = input_voltage_probe_scale
        self.output_voltage_probe_scale = output_voltage_probe_scale
        self.current_probe_scale = current_probe_scale
        self.board = self.instantiate_board(board, board_port)
        self.timeout = 5000
        self.post_processor = post_processor.PostProcessor()

    class TestParameters():
        def __init__(self, positive_voltage_peak, negative_voltage_peak, current_peak, pulses_periods, steady_period=None, dc_bias_current=0, first_pulse_width=None):
            self.positive_voltage_peak = positive_voltage_peak
            self.negative_voltage_peak = negative_voltage_peak
            self.current_peak = current_peak
            self.pulses_periods = pulses_periods
            self.total_time = sum(pulses_periods)
            self.steady_period = steady_period  # Half-period of the switching frequency
            self.dc_bias_current = dc_bias_current  # Target DC bias current (TPT)
            self.first_pulse_width = first_pulse_width  # Width of first pulse for DC buildup

    def set_timeout_in_ms(self, timeout):
        self.timeout = timeout

    def instantiate_power_supply(self, power_supply, port):
        power_supply = PowerSupply.factory(power_supply, port)
        return power_supply

    def instantiate_oscilloscope(self, oscilloscope, port):
        oscilloscope = Oscilloscope.factory(oscilloscope, port)
        return oscilloscope

    def instantiate_board(self, board, port):
        board = Board.factory(board, port)
        return board

    def setup_power_supply(self, parameters, startup=True):
        if startup:
            self.power_supply.disable_output(
                channel=1
            )
            self.power_supply.disable_output(
                channel=2
            )
            self.power_supply.reset_limits()
            # Set current limit high enough to not trip
            self.power_supply.set_current_limit(channel=1, limit=2.0)
            self.power_supply.set_current_limit(channel=2, limit=2.0)

            # result = self.power_supply.enable_series_mode()
            # assert result, "Power supply did not enter series mode"

        print(f"parameters.positive_voltage_peak: {parameters.positive_voltage_peak}")
        print(f"parameters.negative_voltage_peak: {parameters.negative_voltage_peak}")
        self.power_supply.set_source_voltage(
            channel=1,
            voltage=parameters.positive_voltage_peak
        )
        read_voltage = float(round(self.power_supply.get_source_voltage(channel=1), 3))
        assert float(round(parameters.positive_voltage_peak, 3)) == read_voltage, f"Wrong voltage measured at PSU: {read_voltage}, expected {float(round(parameters.positive_voltage_peak, 3))}"

        self.power_supply.set_source_voltage(
            channel=2,
            voltage=parameters.negative_voltage_peak
        )
        read_voltage = float(round(self.power_supply.get_source_voltage(channel=2), 3))
        assert float(round(parameters.negative_voltage_peak, 3)) == read_voltage, f"Wrong voltage measured at PSU: {read_voltage}, expected {float(round(parameters.negative_voltage_peak, 3))}"

    def setup_oscilloscope(self, parameters):
        self.oscilloscope.set_channel_configuration(
            channel=0, 
            input_voltage_range=2 * parameters.positive_voltage_peak / self.input_voltage_probe_scale,
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_channel_configuration(
            channel=1, 
            input_voltage_range=2 * parameters.positive_voltage_peak / self.output_voltage_probe_scale,
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_channel_configuration(
            channel=2, 
            # Probe scale is A/V, so scope voltage = current / probe_scale
            input_voltage_range=parameters.current_peak / self.current_probe_scale,
            # input_voltage_range=1, 
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_rising_trigger(
            channel=0,
            # Use lower threshold to trigger reliably even with ringing/noise
            threshold_voltage=parameters.positive_voltage_peak * 0.2,  # 20% of expected voltage (1.0V for 5V)
            timeout=self.timeout
        )
        self.oscilloscope.arm_trigger(
            channel=0
        )

        # Calculate appropriate number of samples and sampling time
        # Target: ~100 samples per pulse period for good resolution
        # Use steady_period (half of frequency period) as the reference, not min of pulses_periods
        # because pulses_periods may include padding which is much smaller
        if hasattr(parameters, 'steady_period'):
            reference_period = parameters.steady_period
        else:
            # Filter out very short padding periods (anything < 10% of the longest)
            max_period = max(parameters.pulses_periods) if parameters.pulses_periods else 1e-6
            actual_pulse_periods = [p for p in parameters.pulses_periods if p >= max_period * 0.5]
            reference_period = min(actual_pulse_periods) if actual_pulse_periods else max_period
        samples_per_pulse = 100
        
        # Calculate desired sampling time from signal characteristics
        desired_sampling_time = reference_period / samples_per_pulse
        
        # First calculate number of samples needed for the total capture time
        # Use minimum sampling time (4ns for 2408B) for estimation
        min_sampling_time = 4e-9  # Conservative estimate
        estimated_sampling_time = max(desired_sampling_time, min_sampling_time)
        
        # Calculate number of samples (add 20% margin)
        desired_number_samples = int(parameters.total_time * 1.2 / estimated_sampling_time)
        max_samples = 100000  # Practical limit for fast acquisition
        number_samples = min(desired_number_samples, max_samples)
        number_samples = max(number_samples, 1000)  # At least 1000 samples
        
        # IMPORTANT: Set number of samples BEFORE setting sampling time
        self.oscilloscope.set_number_samples(number_samples)
        
        # Now set sampling time (will use the correct number_samples internally)
        actual_sampling_time = self.oscilloscope.set_sampling_time(desired_sampling_time)
        
        print(f"Capture config: {number_samples} samples, {actual_sampling_time*1e9:.1f} ns/sample, total={number_samples*actual_sampling_time*1e6:.1f} µs")
        
        self.oscilloscope.set_channel_label(
            channel=0,
            label="Input Voltage"
        )
        self.oscilloscope.set_channel_label(
            channel=1,
            label="Output Voltage"
        )
        self.oscilloscope.set_channel_label(
            channel=2,
            label="Current"
        )

        self.oscilloscope.set_probe_scale(0, self.input_voltage_probe_scale)
        self.oscilloscope.set_probe_scale(1, self.output_voltage_probe_scale)
        self.oscilloscope.set_probe_scale(2, self.current_probe_scale)

        # self.oscilloscope.set_channel_skew(0, 2e-9)  # TODO: Totally made up skew
        # self.oscilloscope.set_channel_skew(1, 0)
        # self.oscilloscope.set_channel_skew(2, 5e-9)  # TODO: Totally made up skew

    def setup_board(self, parameters):
        self.board.reset()
        self.board.clear_pulses()
        for pulse_period in parameters.pulses_periods:
            self.board.add_pulse(
                pulse_period=pulse_period
            )

    def correct_voltages(self, parameters, voltage_correction):
        parameters.positive_voltage_peak -= voltage_correction
        parameters.negative_voltage_peak += voltage_correction

        return parameters


class CoreLossesMeasurement(Measurement):

    class MeasureParameters():
        def __init__(self, effective_area, number_turns, magnetic_flux_density_ac_peak_to_peak, magnetic_flux_density_dc_bias, frequency, inductance):
            self.effective_area = effective_area
            self.number_turns = number_turns
            self.magnetic_flux_density_ac_peak_to_peak = magnetic_flux_density_ac_peak_to_peak
            self.magnetic_flux_density_dc_bias = magnetic_flux_density_dc_bias
            self.frequency = frequency
            self.inductance = inductance

    def __init__(self, power_supply, oscilloscope, board, power_supply_port, oscilloscope_port, board_port, input_voltage_probe_scale=1, output_voltage_probe_scale=1, current_probe_scale=1):
        super().__init__(power_supply, oscilloscope, board, power_supply_port, oscilloscope_port, board_port, input_voltage_probe_scale, output_voltage_probe_scale, current_probe_scale)
        self.maximum_voltage_error = 0.05
        self.voltage_correction = 0
        self.measured_inductance = None
        self.desired_current_dc_bias = 0

    def set_maximum_voltage_error(self, maximum_voltage_error):
        self.maximum_voltage_error = maximum_voltage_error

    def calculate_test_parameters(self, measure_parameters):
        steady_period = 1.0 / (2 * measure_parameters.frequency)
        voltage_peak_to_peak = measure_parameters.effective_area * measure_parameters.number_turns * measure_parameters.magnetic_flux_density_ac_peak_to_peak / steady_period
        steady_repetitions = 64  # hardcoded

        dc_bias_period = measure_parameters.effective_area * measure_parameters.number_turns * measure_parameters.magnetic_flux_density_dc_bias / (voltage_peak_to_peak / 2)
        current_peak_to_peak = measure_parameters.magnetic_flux_density_ac_peak_to_peak * measure_parameters.number_turns * measure_parameters.effective_area / measure_parameters.inductance
        current_dc_bias = measure_parameters.magnetic_flux_density_dc_bias * measure_parameters.number_turns * measure_parameters.effective_area / measure_parameters.inductance
        current_peak = current_dc_bias * current_peak_to_peak / 2
        self.desired_current_dc_bias = current_dc_bias

        print(f"current_peak: {current_peak}")
        print(f"measure_parameters.effective_area: {measure_parameters.effective_area}")

        print(f"steady_period: {steady_period}")
        print(f"voltage_peak_to_peak: {voltage_peak_to_peak}")
        print(f"current_dc_bias: {current_dc_bias}")
        print(f"current_peak: {current_peak}")
        print(f"current_peak_to_peak: {current_peak_to_peak}")
        print(f"self.voltage_correction: {self.voltage_correction}")

        # pulses_periods = [dc_bias_period]
        pulses_periods = []
        pulses_periods.extend([steady_period, steady_period] * steady_repetitions)

        parameters = self.TestParameters(voltage_peak_to_peak + self.voltage_correction, voltage_peak_to_peak - self.voltage_correction, current_peak, pulses_periods)

        return parameters

    def get_pulses(self, parameters, data):
        number_upsampled_pre_trigger_samples = self.oscilloscope.get_number_upsampled_pre_trigger_samples()
        upsampled_sampling_time = self.oscilloscope.get_upsampled_sampling_time()

        dc_bias_number_samples = int(parameters.pulses_periods[0] / upsampled_sampling_time)
        pulses_data = []
        previous_pulses_number_samples = number_upsampled_pre_trigger_samples + dc_bias_number_samples
        for pulse_pair_index in range(1, len(parameters.pulses_periods) - 1, 2):
            pulse_pair_number_samples = int((parameters.pulses_periods[pulse_pair_index] + parameters.pulses_periods[pulse_pair_index + 1]) / upsampled_sampling_time)
            pulses_datum = data.iloc[previous_pulses_number_samples: previous_pulses_number_samples + pulse_pair_number_samples]
            previous_pulses_number_samples += pulse_pair_number_samples
            pulses_data.append(pulses_datum)

        return pulses_data

    def get_average_peak_output_voltage_pulses(self, parameters, data):
        pulses_data = self.get_pulses(parameters, data)
        last_pulse_data = pulses_data[-1]
        positive_data = last_pulse_data[last_pulse_data["Output Voltage"] > 0]
        negative_data = last_pulse_data[last_pulse_data["Output Voltage"] < 0].abs()
        return positive_data.mean()["Output Voltage"], negative_data.mean()["Output Voltage"]

    def calculate_core_losses(self, parameters, data):
        upsampled_sampling_time = self.oscilloscope.get_upsampled_sampling_time()
        pulses_data = self.get_pulses(parameters, data)

        energy = pulses_data[-1]["Output Voltage"] * pulses_data[-1]["Current"]
        core_losses = energy.sum() * upsampled_sampling_time
        return core_losses

    def run_test(self, measure_parameters):
        plot = True
        adjust_voltage_proportion = True
        parameters = self.calculate_test_parameters(measure_parameters)

        self.setup_power_supply(parameters)
        self.setup_oscilloscope(parameters)
        self.setup_board(parameters)

        data = None
        adjusted_parameters = copy.deepcopy(parameters)
        iteration = 0
        while data is None:

            self.power_supply.enable_output(
                channel=1
            )
            self.power_supply.enable_output(
                channel=2
            )

            print("Running block acquisition")
            self.oscilloscope.run_acquisition_block()

            time.sleep(1)
            print("Running pulses")
            self.board.run_pulses(
                number_repetitions=1
            )

            print("Reading data")
            data = self.oscilloscope.read_data()
            data.to_csv(f"test_data_gas_{iteration}.csv")
            print("Trigger!!")

            self.power_supply.disable_output(
                channel=1
            )
            self.power_supply.disable_output(
                channel=2
            )

            if plot:
                plt.plot(data["time"], data["Input Voltage"])
                # plt.plot(data["time"], data["Output Voltage"])
                # plt.plot(data["time"], data["Output Voltage"] + data["Input Voltage"])
                plt.plot(data["time"], data["Current"])
                plt.show()

            error, best_loop = self.post_processor.analyze_loops(data)
            if adjust_voltage_proportion:
                print("Adjusting voltage")
                cleaned_data = self.post_processor.analyze_loops(data)
                self.voltage_correction = -(cleaned_data["Output Voltage Clean"].max() + cleaned_data["Output Voltage Clean"].min()) / 2

                if abs(self.voltage_correction) / adjusted_parameters.positive_voltage_peak < 0.05:
                    break

                adjusted_parameters = self.calculate_test_parameters(measure_parameters)
                self.setup_power_supply(adjusted_parameters)
                data = None
                iteration += 1

        core_losses = self.calculate_core_losses(adjusted_parameters, data)

        print(f"core_losses: {core_losses} W")

        self.power_supply.disable_output(
            channel=1
        )
        self.power_supply.disable_output(
            channel=2
        )

        return core_losses, data


class InductanceMeasurement(Measurement):
    """
    Inductance Measurement using TPT (Trapezoidal Pulse Testing) Method.
    
    This class measures inductance by applying voltage pulses to an inductor
    and analyzing the current slope: L = V × dt / dI
    
    KEY CONCEPTS
    ------------
    
    1. **Basic Inductance Measurement**
       - Apply known voltage V for time dt
       - Measure resulting current change dI
       - Calculate L = V × dt / dI
       
    2. **Flux and Current Relationship**
       - Flux linkage: λ = L × I = N × Φ = N × B × Ae
       - During voltage pulse: dλ/dt = V, so Δλ = V × dt
       - Current change: ΔI = Δλ / L = V × dt / L
       
    3. **Saturation Detection**
       - As core saturates, permeability μ drops, so L drops
       - This causes dI/dt to increase for same V
       - Monitor for sudden increase in current slope
       
    4. **DC Bias Measurement (TPT Method)**
       - First long pulse builds up DC current: I_dc = V × t_long / L
       - Subsequent measurement pulses ride on this DC bias
       - Allows measuring L(I) saturation curve
    
    CRITICAL PARAMETERS
    -------------------
    
    **current_probe_scale**: Conversion factor for probe voltage to current
        - For 100 mV/A probe: scale = 0.1 (Current = Voltage × 0.1)
        - For 1 V/A probe: scale = 1.0
        - IMPORTANT: This is multiplication, not division!
        
    **Frequency Selection**:
        - Higher frequency → lower flux swing → safer for saturation testing
        - Lower frequency → higher flux → better L accuracy but risk saturation
        - Typical: Start at 100kHz-500kHz, sweep down to 1kHz-10kHz
        
    **Voltage Selection**:
        - Higher voltage → larger dI → better signal-to-noise
        - But also higher flux → risk of saturation
        - Balance between measurement accuracy and safety
    
    FLUX BALANCE
    ------------
    
    For accurate measurements without DC bias:
    - Use `create_balanced_pulse_train()` which creates even half-period count
    - Use `demagnetize()` before and after measurements
    - Avoid using pulse trains with odd half-periods or unbalanced padding
    
    METHODS SUMMARY
    ---------------
    
    Core Measurement:
        - `calculate_test_parameters()`: Create pulse train for basic L measurement
        - `calculate_dc_bias_parameters()`: Create pulse train with DC bias (TPT)
        - `run_measurement()`: Execute single-point measurement
        - `run_frequency_sweep()`: Sweep frequency to characterize L(f)
        - `run_dc_bias_measurement()`: Measure L at specific DC bias point
        
    Flux Management:
        - `demagnetize()`: Reset core flux to zero with decreasing pulses
        - `create_balanced_pulse_train()`: Create zero-DC pulse train
        
    Analysis:
        - `calculate_inductance_from_slope()`: Extract L from captured waveform
        - `calculate_theoretical_inductance()`: Compute expected L from core geometry
    
    EXAMPLE WORKFLOW
    ----------------
    
    1. Initialize measurement system
    2. Call `demagnetize()` to ensure clean starting state
    3. Create test parameters with `calculate_test_parameters()` or 
       `create_balanced_pulse_train()`
    4. Configure oscilloscope channels and trigger
    5. Run pulse train and capture waveform
    6. Extract inductance with `calculate_inductance_from_slope()`
    7. Call `demagnetize()` to clean up
    
    KNOWN ISSUES / TODO
    -------------------
    
    - Measured L may differ from Bode100 by ~20-30% due to frequency-dependent
      permeability and measurement method differences
    - DC bias measurement requires working CH2 on power supply (negative rail)
    - Current probe scale must be correctly configured (common error source)
    """
    
    # Core database - add more cores as needed
    CORE_DATABASE = {
        'RM10': {
            'effective_area': 96.6e-6,      # m² (Ae)
            'effective_length': 44.6e-3,    # m (le)
            'effective_volume': 4310e-9,    # m³ (Ve)
        },
        'RM8': {
            'effective_area': 64.0e-6,
            'effective_length': 38.0e-3,
            'effective_volume': 2430e-9,
        },
        'RM12': {
            'effective_area': 146e-6,
            'effective_length': 52.0e-3,
            'effective_volume': 7590e-9,
        },
    }
    
    # Material database
    MATERIAL_DATABASE = {
        'N87': {
            'initial_permeability': 2200,
            'saturation_flux_density': 0.39,  # T at 100°C (conservative)
        },
        'N97': {
            'initial_permeability': 2300,
            'saturation_flux_density': 0.41,
        },
        'N49': {
            'initial_permeability': 1500,
            'saturation_flux_density': 0.49,
        },
    }
    
    class MeasureParameters():
        def __init__(self, 
                     core_type='RM10',
                     material='N87',
                     number_turns=26,
                     air_gap=0,  # meters, 0 for ungapped
                     start_voltage=1.0,
                     max_voltage=10.0,
                     start_frequency=500000,
                     min_frequency=1000,
                     frequency_steps=25,
                     saturation_threshold=0.20,
                     max_flux_density=0.30,  # T - stop before saturation
                     max_current=10.0,
                     num_pulses=2):
            """
            Parameters for inductance measurement with saturation detection.
            
            Core Parameters:
                core_type: Core geometry (e.g., 'RM10', 'RM8')
                material: Core material (e.g., 'N87', 'N97')
                number_turns: Number of winding turns
                air_gap: Air gap in meters (0 for ungapped)
            
            Test Parameters:
                start_voltage: Initial test voltage (V)
                max_voltage: Maximum test voltage (V)
                start_frequency: Starting frequency (Hz) - high = safe
                min_frequency: Minimum frequency to sweep to (Hz)
                frequency_steps: Number of frequency points
                saturation_threshold: Relative inductance drop to detect saturation
                max_flux_density: Maximum B before stopping (T)
                max_current: Maximum allowed current (A)
                num_pulses: Number of pulses per measurement
            """
            self.core_type = core_type
            self.material = material
            self.number_turns = number_turns
            self.air_gap = air_gap
            self.start_voltage = start_voltage
            self.max_voltage = max_voltage
            self.start_frequency = start_frequency
            self.min_frequency = min_frequency
            self.frequency_steps = frequency_steps
            self.saturation_threshold = saturation_threshold
            self.max_flux_density = max_flux_density
            self.max_current = max_current
            self.num_pulses = num_pulses

    class MeasurementResult():
        def __init__(self):
            self.frequencies = []
            self.inductances = []
            self.peak_currents = []
            self.flux_densities = []
            self.saturation_detected = False
            self.saturation_frequency = None
            self.nominal_inductance = None
            self.theoretical_inductance = None
            
        def add_point(self, frequency, inductance, peak_current, flux_density=0):
            self.frequencies.append(frequency)
            self.inductances.append(inductance)
            self.peak_currents.append(peak_current)
            self.flux_densities.append(flux_density)
            
        def to_dataframe(self):
            import pandas as pd
            return pd.DataFrame({
                'frequency_Hz': self.frequencies,
                'inductance_H': self.inductances,
                'inductance_mH': [L * 1e3 for L in self.inductances],
                'peak_current_A': self.peak_currents,
                'flux_density_mT': [B * 1e3 for B in self.flux_densities]
            })

    def __init__(self, power_supply, oscilloscope, board, power_supply_port, oscilloscope_port, board_port, input_voltage_probe_scale=1, output_voltage_probe_scale=1, current_probe_scale=1):
        super().__init__(power_supply, oscilloscope, board, power_supply_port, oscilloscope_port, board_port, input_voltage_probe_scale, output_voltage_probe_scale, current_probe_scale)
        self.plot_each_measurement = False
        self.verbose = True
        self._last_voltage = None  # Track voltage to avoid redundant PSU setup
        self._psu_initialized = False

    def demagnetize(self, max_voltage=10.0, frequency=10000, num_steps=10, pulses_per_step=2):
        """
        Demagnetize the inductor core by applying decreasing alternating voltage pulses.
        
        This ensures the magnetic flux returns to zero after measurements, especially
        important after tests with DC bias or asymmetric voltages that leave residual
        magnetization.
        
        The method applies symmetric alternating pulses with decreasing amplitude,
        similar to AC demagnetization used in magnetic materials.
        
        Args:
            max_voltage: Starting voltage amplitude in V (default 10V)
            frequency: Frequency of the demagnetizing pulses in Hz (default 10kHz)
            num_steps: Number of amplitude steps from max to zero (default 10)
            pulses_per_step: Number of complete cycles at each amplitude (default 2)
            
        Returns:
            bool: True if demagnetization completed successfully
        """
        if self.verbose:
            print(f"Demagnetizing: {num_steps} steps from {max_voltage}V to 0V at {frequency/1000:.0f}kHz")
        
        steady_period = 1.0 / (2 * frequency)
        
        # Calculate voltage steps (decreasing from max to near zero)
        voltage_steps = [max_voltage * (num_steps - i) / num_steps for i in range(num_steps)]
        
        try:
            for step, voltage in enumerate(voltage_steps):
                if voltage < 0.5:  # Skip very low voltages
                    continue
                    
                # Set symmetric voltages
                self.power_supply.set_source_voltage(channel=1, voltage=voltage)
                self.power_supply.set_source_voltage(channel=2, voltage=voltage)
                
                # Create balanced pulse train (even number of half-periods)
                # This ensures we end at zero current/flux
                pulses_periods = [steady_period, steady_period] * pulses_per_step
                
                # Setup and run pulses
                self.board.reset()
                self.board.clear_pulses()
                for pulse_period in pulses_periods:
                    self.board.add_pulse(pulse_period=pulse_period)
                
                self.power_supply.enable_output(channel=1)
                self.power_supply.enable_output(channel=2)
                
                time.sleep(0.01)  # Short settling time
                self.board.run_pulses(number_repetitions=1)
                time.sleep(0.02)  # Wait for pulses to complete
                
                self.power_supply.disable_output(channel=1)
                self.power_supply.disable_output(channel=2)
            
            # Final step: ensure outputs are off and at safe voltage
            self.power_supply.set_source_voltage(channel=1, voltage=0)
            self.power_supply.set_source_voltage(channel=2, voltage=0)
            self.power_supply.disable_output(channel=1)
            self.power_supply.disable_output(channel=2)
            
            if self.verbose:
                print("Demagnetization complete - flux reset to zero")
            
            # Reset PSU tracking since we changed voltages
            self._last_voltage = None
            
            return True
            
        except Exception as e:
            print(f"Demagnetization error: {e}")
            self.power_supply.disable_output(channel=1)
            self.power_supply.disable_output(channel=2)
            return False

    def create_balanced_pulse_train(self, voltage, frequency, num_pulses):
        """
        Create a pulse train that ends with zero net flux (balanced volt-seconds).
        
        FLUX BALANCE EXPLANATION
        ------------------------
        For zero residual magnetization, the volt-seconds must be balanced:
        
            ∫V dt (positive) = ∫V dt (negative)
        
        With symmetric voltages (+V and -V) and equal pulse widths (T/2 each),
        this requires an EVEN number of half-periods:
        
            Pattern: +V(T/2), -V(T/2), +V(T/2), -V(T/2), ...
            
        If we have 8 half-periods: +V, -V, +V, -V, +V, -V, +V, -V
        Net volt-seconds = 4×(+V×T/2) + 4×(-V×T/2) = 0  ✓
        
        WARNING: Adding padding at the end (like calculate_test_parameters does)
        creates an odd number of periods and leaves residual flux!
        
        Args:
            voltage: Voltage amplitude in V (symmetric +/-)
            frequency: Switching frequency in Hz  
            num_pulses: Number of complete cycles (each cycle = 2 half-periods)
                       Total half-periods = 2 × num_pulses (always even)
            
        Returns:
            TestParameters with balanced pulse train
            
        Example:
            >>> params = meas.create_balanced_pulse_train(10, 100000, 4)
            >>> # Creates 8 half-periods at 100kHz: [5us, 5us, 5us, 5us, 5us, 5us, 5us, 5us]
            >>> # Total time = 40us, zero net flux at end
        """
        steady_period = 1.0 / (2 * frequency)
        
        # Estimate current for scope range
        L_estimate = 0.004  # 4 mH estimate
        expected_ripple = voltage / (2 * frequency * L_estimate)
        current_peak = expected_ripple * 5  # 5x margin for ripple only (no DC buildup)
        current_peak = max(current_peak, 0.050)
        current_peak = min(current_peak, 2.0)
        
        # Create balanced pulse train: exactly 2*num_pulses half-periods (even count)
        # Pattern: +V, -V, +V, -V, ... ending with -V
        pulses_periods = [steady_period] * (2 * num_pulses)
        
        parameters = self.TestParameters(
            positive_voltage_peak=voltage,
            negative_voltage_peak=voltage,
            current_peak=current_peak,
            pulses_periods=pulses_periods,
            steady_period=steady_period
        )
        
        if self.verbose:
            print(f"  Balanced pulse train: {2*num_pulses} half-periods, ends at zero flux")
        
        return parameters

    def calculate_test_parameters(self, voltage, frequency, num_pulses):
        """
        Calculate test parameters for a single frequency point.
        
        NOTE: This method adds padding at the end for minimum capture time,
        which can create an ODD number of half-periods. For measurements
        requiring zero DC flux, use `create_balanced_pulse_train()` instead.
        
        WARNING - FLUX IMBALANCE
        ------------------------
        If total_pulse_time < 200us, this method adds padding:
        
            [5us, 5us, 5us, 5us, 5us, 5us, 5us, 5us] → 40us
            + padding: 160us
            = [5us, 5us, 5us, 5us, 5us, 5us, 5us, 5us, 160us] → 9 periods!
            
        This leaves the core magnetized at the end (odd half-periods).
        For consecutive measurements, call `demagnetize()` between tests.
        
        Args:
            voltage: Test voltage in V
            frequency: Test frequency in Hz
            num_pulses: Number of complete cycles
            
        Returns:
            TestParameters with pulse train (may have padding)
        """
        steady_period = 1.0 / (2 * frequency)
        
        # Dynamic current range based on frequency
        # For inductance measurement, we need to capture the current ripple
        # ΔI = V × dt / L = V / (2 × f × L)
        # But DC builds up across pulses, so we need much more headroom
        L_estimate = 0.004  # 4 mH estimate
        expected_ripple = voltage / (2 * frequency * L_estimate)
        
        # Peak current includes DC buildup across pulses - use 20x margin
        # The DC builds up because current doesn't fully reset between pulse trains
        current_peak = expected_ripple * 20
        current_peak = max(current_peak, 0.100)  # Minimum 100 mA range
        current_peak = min(current_peak, 2.0)  # Maximum 2 A range
        
        # Create pulse train
        # Each pulse is: positive half-period + negative half-period
        pulses_periods = [steady_period, steady_period] * num_pulses
        
        # Ensure minimum capture time for good scope resolution
        # At least 100 samples per pulse at 4ns/sample = 400ns minimum pulse
        min_capture_time = 200e-6  # 200 us minimum capture
        total_pulse_time = sum(pulses_periods)
        if total_pulse_time < min_capture_time:
            # Add padding at the end
            pulses_periods.append(min_capture_time - total_pulse_time)
        
        parameters = self.TestParameters(
            positive_voltage_peak=voltage,
            negative_voltage_peak=voltage,
            current_peak=current_peak,
            pulses_periods=pulses_periods,
            steady_period=steady_period  # Pass the actual pulse period for timing calculations
        )
        
        # Debug: show current range being used
        if self.verbose:
            voltage_range = current_peak / self.current_probe_scale  # V = I / probe_scale (probe_scale is A/V)
            print(f"  Current range: {current_peak*1000:.1f} mA (ripple={expected_ripple*1000:.2f} mA), Scope range: {voltage_range*1000:.1f} mV")
        
        return parameters

    def smooth_signal(self, signal, window_size=5):
        """
        Apply a moving average filter to smooth noisy signals.
        
        Args:
            signal: numpy array of signal values
            window_size: Size of the averaging window (default 5)
            
        Returns:
            Smoothed signal array (same length as input)
        """
        import numpy as np
        if len(signal) < window_size:
            return signal
        
        # Use numpy convolve for efficient moving average
        kernel = np.ones(window_size) / window_size
        # 'same' mode returns array of same length
        smoothed = np.convolve(signal, kernel, mode='same')
        
        # Fix edge effects by using original values at edges
        half_win = window_size // 2
        smoothed[:half_win] = signal[:half_win]
        smoothed[-half_win:] = signal[-half_win:]
        
        return smoothed

    def calculate_inductance_from_slope(self, data, voltage, smooth_current=True, smooth_window=7):
        """
        Calculate inductance from current slope during voltage pulses.
        
        FUNDAMENTAL RELATIONSHIP
        ------------------------
        For an inductor: V = L × dI/dt
        
        Rearranging: L = V / (dI/dt) = V × dt / dI
        
        During a voltage pulse:
            - V is the applied voltage (known from PSU setting, verified from scope)
            - dI/dt is measured from the current waveform slope
            - L is calculated from these values
        
        MEASUREMENT PROCEDURE
        ---------------------
        1. Find regions where voltage is positive (above threshold)
        2. For each positive pulse:
           a. Skip edge regions (ringing, switching transients)
           b. Use linear regression on middle portion for robust slope
           c. Calculate L = V_avg / slope
        3. Return inductance from first pulse (cleanest, no DC buildup effects)
        
        NOISE HANDLING
        --------------
        - Optional smoothing filter reduces high-frequency noise
        - Linear regression (least squares) is more robust than endpoint method
        - Dynamic margin skips pulse edges where ringing occurs
        - Uses actual measured voltage (not just setpoint) for accuracy
        
        IMPORTANT CONSIDERATIONS
        ------------------------
        1. **DC Buildup**: Without proper demagnetization, DC current accumulates
           across pulses, causing apparent L variation between pulses.
           
        2. **Probe Scale**: The current values must be correctly scaled!
           Current_A = Scope_V × probe_scale
           For 100mV/A probe: probe_scale = 0.1
           
        3. **Frequency Effects**: At high frequencies:
           - Ringing takes relatively longer portion of pulse
           - Winding capacitance affects measurement
           - Core permeability may be frequency-dependent
           
        4. **Slope Sign**: dI/dt is positive during positive voltage pulse
           for a normal inductor. If negative, check connections/polarity.
        
        Args:
            data: DataFrame with columns:
                  - 'time': Time in seconds
                  - 'Current': Current in Amps (already scaled by probe_scale)
                  - 'Input Voltage': Voltage across inductor in Volts
            voltage: Expected voltage level in V (used for threshold detection)
            smooth_current: Whether to apply smoothing filter (default True)
            smooth_window: Size of smoothing window (default 7 samples)
        
        Returns:
            tuple: (inductance in H, peak current in A, slopes list)
                   - inductance: Calculated L from first pulse
                   - peak current: Maximum current observed
                   - slopes: List of (slope, L, V) tuples for each pulse
                   
        Example:
            >>> L, I_peak, slopes = meas.calculate_inductance_from_slope(data, voltage=10)
            >>> print(f"L = {L*1000:.2f} mH, I_peak = {I_peak*1000:.1f} mA")
        """
        import numpy as np
        
        time = data["time"].values
        current = data["Current"].values
        input_voltage = data["Input Voltage"].values
        
        # Apply smoothing to reduce noise
        if smooth_current:
            current = self.smooth_signal(current, smooth_window)
        
        # Find regions where voltage is positive (positive pulse)
        voltage_threshold = voltage * 0.5
        positive_regions = input_voltage > voltage_threshold
        
        # Find transitions (rising edges of voltage)
        transitions = []
        in_positive = False
        start_idx = None
        
        for i in range(1, len(positive_regions)):
            if positive_regions[i] and not in_positive:
                # Rising edge - start of positive pulse
                start_idx = i
                in_positive = True
            elif not positive_regions[i] and in_positive:
                # Falling edge - end of positive pulse
                if start_idx is not None:
                    transitions.append((start_idx, i))
                in_positive = False
        
        if len(transitions) < 1:
            return None, None, []
        
        # Calculate slope for each positive pulse
        slopes = []
        for start_idx, end_idx in transitions:
            # Use middle portion of the pulse to avoid edge effects (ringing, overshoot)
            # At high frequencies, ringing takes longer relative to pulse width, so use larger margin
            pulse_length = end_idx - start_idx
            
            # Dynamic margin: 30% at each end for short pulses, 20% for longer pulses
            if pulse_length < 50:
                margin_fraction = 0.30  # 40% usable for short pulses
            elif pulse_length < 100:
                margin_fraction = 0.25  # 50% usable for medium pulses
            else:
                margin_fraction = 0.20  # 60% usable for long pulses
            
            margin = int(pulse_length * margin_fraction)
            
            if pulse_length < 10:
                continue
                
            segment_start = start_idx + margin
            segment_end = end_idx - margin
            
            if segment_end <= segment_start + 5:  # Need at least 5 points
                continue
            
            t_segment = time[segment_start:segment_end]
            i_segment = current[segment_start:segment_end]
            v_segment = input_voltage[segment_start:segment_end]
            
            if len(t_segment) < 5:
                continue
            
            # Use actual measured voltage (average during slope region)
            avg_voltage = sum(v_segment) / len(v_segment)
            
            # Use linear regression (least squares) for robust slope calculation
            # This is much more noise-resistant than endpoint-to-endpoint
            n = len(t_segment)
            t_mean = sum(t_segment) / n
            i_mean = sum(i_segment) / n
            
            # Calculate slope using least squares: slope = Σ(t-t_mean)(i-i_mean) / Σ(t-t_mean)²
            numerator = sum((t - t_mean) * (i - i_mean) for t, i in zip(t_segment, i_segment))
            denominator = sum((t - t_mean) ** 2 for t in t_segment)
            
            if denominator > 0:
                slope = numerator / denominator  # dI/dt in A/s
                # Calculate inductance for this pulse using measured voltage
                if abs(slope) > 0.001:
                    pulse_inductance = abs(avg_voltage / slope)
                    slopes.append((slope, pulse_inductance, avg_voltage))
        
        if not slopes:
            return None, None, []
        
        # DC current builds up across pulses because the system doesn't fully reset
        # This causes decreasing dI/dt (apparent increasing L) for later pulses
        # Only use the first pulse which starts from zero current
        # Or use pulses where current starts near zero (within 10% of peak)
        
        first_L = slopes[0][1]  # Inductance from first pulse
        first_slope = slopes[0][0]
        first_voltage = slopes[0][2]
        
        # Calculate stats for debug output
        inductances = [s[1] for s in slopes]
        if len(inductances) > 1:
            variance = sum((L - first_L)**2 for L in inductances) / (len(inductances) - 1)
            std_dev = variance ** 0.5
            std_pct = std_dev / first_L * 100 if first_L > 0 else 0
        else:
            std_pct = 0
        
        # Print debug info
        if std_pct > 30:
            print(f"  Using first pulse only (DC buildup detected, later pulses vary by {std_pct:.0f}%)")
        else:
            print(f"  Averaged {len(slopes)} pulses (std: {std_pct:.1f}%)")
        print(f"  Using measured voltage: {first_voltage:.2f} V")
        
        peak_current = max(abs(current))
        
        return first_L, peak_current, [s[0] for s in slopes]

    def detect_saturation(self, result, threshold):
        """
        Detect if saturation has occurred based on inductance drop.
        
        Saturation is detected when inductance drops by more than threshold
        compared to the initial (nominal) inductance.
        
        Args:
            result: MeasurementResult with inductance data
            threshold: Relative drop threshold (e.g., 0.2 = 20% drop)
            
        Returns:
            bool: True if saturation detected
        """
        # Need at least 4 measurements before detecting saturation
        if len(result.inductances) < 4:
            return False
        
        # Use average of first few measurements as nominal inductance
        num_nominal = min(3, len(result.inductances))
        nominal_inductance = sum(result.inductances[:num_nominal]) / num_nominal
        result.nominal_inductance = nominal_inductance
        
        # Check if latest inductance has dropped significantly
        latest_inductance = result.inductances[-1]
        
        if nominal_inductance > 0:
            relative_drop = (nominal_inductance - latest_inductance) / nominal_inductance
            if relative_drop > threshold:
                return True
        
        return False

    def run_single_measurement(self, voltage, frequency, num_pulses, max_retries=5):
        """Run a single inductance measurement at given voltage and frequency.
        
        Returns:
            dict or None: Contains 'data', 'inductance', 'peak_current', 'slopes' if successful
        """
        import numpy as np
        
        parameters = self.calculate_test_parameters(voltage, frequency, num_pulses)
        
        # Only setup power supply if voltage changed (PSU commands are slow)
        if voltage != self._last_voltage or not self._psu_initialized:
            self.setup_power_supply(parameters, startup=not self._psu_initialized)
            self._last_voltage = voltage
            self._psu_initialized = True
        
        self.setup_oscilloscope(parameters)
        self.setup_board(parameters)
        
        self.power_supply.enable_output(channel=1)
        self.power_supply.enable_output(channel=2)
        
        # Calculate expected capture duration for adaptive timing
        capture_duration = self.oscilloscope.number_samples * self.oscilloscope.sampling_time
        
        # Retry loop for unreliable triggering
        best_data = None
        best_quality = 0
        
        for attempt in range(max_retries):
            if attempt > 0:
                # Re-setup oscilloscope and board on retry
                self.setup_oscilloscope(parameters)
                self.setup_board(parameters)
                # Longer delay at lower frequencies
                delay = 0.05 + (0.1 if frequency < 50000 else 0)
                time.sleep(delay)
            
            # Start acquisition - this arms the trigger
            self.oscilloscope.run_acquisition_block()
            
            # Adaptive delay before pulses based on frequency
            # Lower frequencies need more settling time
            if frequency < 30000:
                time.sleep(0.05)  # 50ms for very low frequencies
            elif frequency < 100000:
                time.sleep(0.02)  # 20ms for mid frequencies
            else:
                time.sleep(0.01)  # 10ms for high frequencies
            
            # Fire the pulses
            self.board.run_pulses(number_repetitions=1)
            
            # Wait for acquisition to complete (based on actual capture duration)
            wait_time = max(0.1, capture_duration * 2 + 0.1)
            time.sleep(wait_time)
            
            data = self.oscilloscope.read_data()
            
            # Quality check: need good voltage AND good current resolution
            max_voltage = data["Input Voltage"].max()
            unique_currents = len(np.unique(data["Current"]))
            voltage_ok = max_voltage > voltage * 0.7
            current_ok = unique_currents > 20  # Need reasonable ADC resolution
            
            quality = (1 if voltage_ok else 0) + (1 if current_ok else 0) + unique_currents / 100
            
            if voltage_ok and current_ok:
                # Good capture - calculate inductance immediately
                inductance, peak_current, slopes = self.calculate_inductance_from_slope(data, voltage)
                
                if inductance is not None:
                    self.power_supply.disable_output(channel=1)
                    self.power_supply.disable_output(channel=2)
                    return {
                        'data': data,
                        'inductance': inductance,
                        'peak_current': peak_current,
                        'slopes': slopes,
                        'frequency': frequency,
                        'attempts': attempt + 1
                    }
            
            # Track best attempt even if not perfect
            if quality > best_quality:
                best_quality = quality
                best_data = data
            
            if attempt < max_retries - 1:
                if self.verbose:
                    print(f"  Retry {attempt + 1}: max_V={max_voltage:.2f}, unique_I={unique_currents}")
                time.sleep(0.1)
        
        self.power_supply.disable_output(channel=1)
        self.power_supply.disable_output(channel=2)
        
        # Return best attempt even if not perfect (for debugging)
        if best_data is not None:
            return {'data': best_data, 'inductance': None, 'peak_current': None, 'slopes': [], 'failed': True}
        return None

    def run_frequency_sweep(self, voltage, frequencies, num_pulses=10, max_retries=3, 
                            reference_inductance=None, plot=True, save_plot=True):
        """
        Run inductance measurement across multiple frequencies and optionally plot results.
        
        Args:
            voltage: Test voltage in Volts
            frequencies: List of frequencies in Hz (e.g., [200000, 150000, 100000])
            num_pulses: Number of pulses per measurement (default 10)
            max_retries: Maximum retries per frequency (default 3)
            reference_inductance: Reference inductance in H for comparison line (optional)
            plot: Whether to display plot (default True)
            save_plot: Whether to save plot to file (default True)
            
        Returns:
            dict: Contains 'frequencies', 'inductances', 'peak_currents', 'success_rate'
        """
        import matplotlib.pyplot as plt
        
        results = {
            'frequencies': [],
            'inductances': [],
            'peak_currents': [],
            'raw_results': []
        }
        
        print("=" * 60)
        print("INDUCTANCE FREQUENCY SWEEP")
        print("=" * 60)
        print(f"Voltage: {voltage} V")
        print(f"Frequencies: {[f/1000 for f in frequencies]} kHz")
        print(f"Pulses per measurement: {num_pulses}")
        print("=" * 60)
        
        for freq in frequencies:
            result = self.run_single_measurement(
                voltage=voltage,
                frequency=freq,
                num_pulses=num_pulses,
                max_retries=max_retries
            )
            
            if result and result.get('inductance'):
                L_mH = result['inductance'] * 1000
                I_mA = result['peak_current'] * 1000
                results['frequencies'].append(freq)
                results['inductances'].append(result['inductance'])
                results['peak_currents'].append(result['peak_current'])
                results['raw_results'].append(result)
                print(f"{freq/1000:.0f} kHz: L = {L_mH:.2f} mH, Peak I = {I_mA:.1f} mA")
            else:
                print(f"{freq/1000:.0f} kHz: FAILED")
        
        # Calculate statistics
        if results['inductances']:
            inductances_mH = [L * 1000 for L in results['inductances']]
            results['mean_inductance'] = sum(results['inductances']) / len(results['inductances'])
            results['std_inductance'] = (sum((L - results['mean_inductance'])**2 for L in results['inductances']) / len(results['inductances'])) ** 0.5
            results['success_rate'] = len(results['inductances']) / len(frequencies)
            
            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            print(f"Successful measurements: {len(results['inductances'])}/{len(frequencies)}")
            print(f"Mean inductance: {results['mean_inductance']*1000:.2f} mH")
            print(f"Std deviation: {results['std_inductance']*1000:.2f} mH ({results['std_inductance']/results['mean_inductance']*100:.1f}%)")
            if reference_inductance:
                error = (results['mean_inductance'] - reference_inductance) / reference_inductance * 100
                print(f"Reference: {reference_inductance*1000:.2f} mH, Error: {error:+.1f}%")
            print("=" * 60)
            
            # Plot results
            if plot or save_plot:
                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
                
                freq_kHz = [f/1000 for f in results['frequencies']]
                
                # Inductance plot
                ax1.plot(freq_kHz, inductances_mH, 'bo-', markersize=10, linewidth=2, label='Measured')
                if reference_inductance:
                    ax1.axhline(y=reference_inductance*1000, color='r', linestyle='--', 
                               linewidth=2, label=f'Reference ({reference_inductance*1000:.2f} mH)')
                ax1.axhline(y=results['mean_inductance']*1000, color='g', linestyle=':', 
                           linewidth=2, alpha=0.7, label=f'Mean ({results["mean_inductance"]*1000:.2f} mH)')
                ax1.set_ylabel('Inductance (mH)', fontsize=12)
                ax1.set_title(f'Inductance vs Frequency @ {voltage}V', fontsize=14)
                ax1.grid(True, alpha=0.3)
                ax1.legend()
                ax1.invert_xaxis()
                
                # Peak current plot
                peak_currents_mA = [I*1000 for I in results['peak_currents']]
                ax2.plot(freq_kHz, peak_currents_mA, 'ro-', markersize=10, linewidth=2)
                ax2.set_xlabel('Frequency (kHz)', fontsize=12)
                ax2.set_ylabel('Peak Current (mA)', fontsize=12)
                ax2.set_title('Peak Current vs Frequency', fontsize=14)
                ax2.grid(True, alpha=0.3)
                
                plt.tight_layout()
                
                if save_plot:
                    filename = f'inductance_sweep_{voltage}V.png'
                    plt.savefig(filename, dpi=150)
                    print(f"Plot saved to {filename}")
                
                if plot:
                    plt.show()
                else:
                    plt.close()
        
        return results

    def calculate_dc_bias_parameters(self, voltage, frequency, dc_bias_current, num_measurement_pulses, 
                                      inductance_estimate=0.003):
        """
        Calculate test parameters for TPT (Triple Pulse Test) with DC bias current.
        
        TPT METHOD OVERVIEW
        -------------------
        The Triple Pulse Test is a technique to measure inductance at a specific
        DC bias operating point. This is critical for:
        
        - Characterizing saturation behavior L(I)
        - Measuring inductance under actual operating conditions
        - Determining maximum current before saturation
        
        The method works by:
        1. Applying a first long pulse to build up DC current to the target level
        2. Following with measurement pulses to determine L at that DC point
        
        FIRST PULSE WIDTH CALCULATION
        -----------------------------
        From the TPT paper (equation 7):
        
            t1 = I0 × L / V + 0.5 × T/2
            
        Where:
            I0 = target DC bias current (A)
            L = inductance estimate (H)
            V = applied voltage (V)
            T/2 = half-period of measurement frequency
        
        The 0.5 × T/2 term accounts for the current rise during the first
        half of a normal measurement pulse.
        
        FLUX AND CURRENT BUILDUP
        ------------------------
        During the first pulse:
            Δλ = V × t1 (volt-seconds applied)
            ΔI = Δλ / L = V × t1 / L
            
        After first pulse, current is near I0 and subsequent symmetric pulses
        maintain this DC level while adding AC ripple for measurement.
        
        ALTERNATIVE: ASYMMETRIC VOLTAGE METHOD
        --------------------------------------
        Instead of a long first pulse, you can use asymmetric voltages:
        
            V+ > V- creates net positive volt-seconds per cycle
            
        Example: V+ = 14V, V- = 6V
            Net voltage per cycle = (14 - 6) / 2 = 4V average
            DC current builds up gradually over multiple cycles
            
        This approach is gentler on the core but takes longer to reach DC bias.
        
        Args:
            voltage: Test voltage in V
            frequency: Test frequency in Hz  
            dc_bias_current: Target DC bias current in A
            num_measurement_pulses: Number of measurement pulses after DC bias established
            inductance_estimate: Estimated inductance in H (for calculating first pulse width)
            
        Returns:
            TestParameters with DC bias pulse train
            
        Note:
            The inductance_estimate affects the first pulse width. If the estimate
            is wrong, the actual DC bias current will differ from the target.
            Consider iterating: measure at low DC, use result to refine estimate.
        """
        steady_period = 1.0 / (2 * frequency)  # Half-period for symmetric pulses
        
        # Calculate first pulse width to establish DC bias current
        # t1 = I0 × L / UL + 0.5 × t2 (from TPT paper equation 7)
        t1 = dc_bias_current * inductance_estimate / voltage + 0.5 * steady_period
        
        # Current range needs to account for DC bias plus AC ripple
        # ΔI = V × dt / L
        expected_ripple = voltage * steady_period / inductance_estimate
        current_peak = dc_bias_current + expected_ripple * 2  # DC + margin for ripple
        current_peak = max(current_peak, 0.050)  # Minimum 50 mA
        current_peak = min(current_peak, 2.0)  # Maximum 2 A
        
        # Build pulse train:
        # 1. First pulse (t1) - long pulse to build DC bias current
        # 2. Stabilization pulses - a couple of full cycles to stabilize
        # 3. Measurement pulses - the actual measurement cycles
        
        pulses_periods = []
        
        # First pulse: positive phase to build up current
        pulses_periods.append(t1)
        
        # Negative phase (freewheel/recovery) - same as steady period
        pulses_periods.append(steady_period)
        
        # Stabilization: 2 full cycles
        for _ in range(2):
            pulses_periods.append(steady_period)  # positive
            pulses_periods.append(steady_period)  # negative
        
        # Measurement pulses
        for _ in range(num_measurement_pulses):
            pulses_periods.append(steady_period)  # positive
            pulses_periods.append(steady_period)  # negative
        
        # Ensure minimum capture time
        min_capture_time = 200e-6
        total_pulse_time = sum(pulses_periods)
        if total_pulse_time < min_capture_time:
            pulses_periods.append(min_capture_time - total_pulse_time)
        
        parameters = self.TestParameters(
            positive_voltage_peak=voltage,
            negative_voltage_peak=voltage,
            current_peak=current_peak,
            pulses_periods=pulses_periods,
            steady_period=steady_period,
            dc_bias_current=dc_bias_current,  # Store for reference
            first_pulse_width=t1
        )
        
        if self.verbose:
            voltage_range = current_peak / self.current_probe_scale
            print(f"  DC Bias TPT: I_dc={dc_bias_current*1000:.0f}mA, t1={t1*1e6:.1f}µs")
            print(f"  Current range: {current_peak*1000:.1f} mA, Scope range: {voltage_range*1000:.0f} mV")
        
        return parameters

    def run_dc_bias_measurement(self, voltage, frequency, dc_bias_current, num_pulses=5, 
                                 max_retries=3, inductance_estimate=0.003):
        """
        Run inductance measurement with DC bias current (TPT method).
        
        Uses the Triple Pulse Test approach:
        1. First pulse establishes the DC bias current
        2. Stabilization pulses 
        3. Measurement pulses where inductance is calculated
        
        Args:
            voltage: Test voltage in V
            frequency: Test frequency in Hz
            dc_bias_current: Target DC bias current in A
            num_pulses: Number of measurement pulses (default 5)
            max_retries: Maximum retries (default 3)
            inductance_estimate: Estimated inductance for first pulse calculation (default 3mH)
            
        Returns:
            dict: Contains 'data', 'inductance', 'dc_current', 'ac_ripple' etc.
        """
        import numpy as np
        
        parameters = self.calculate_dc_bias_parameters(
            voltage, frequency, dc_bias_current, num_pulses, inductance_estimate
        )
        
        # Setup hardware
        if voltage != self._last_voltage or not self._psu_initialized:
            self.setup_power_supply(parameters, startup=not self._psu_initialized)
            self._last_voltage = voltage
            self._psu_initialized = True
        
        self.setup_oscilloscope(parameters)
        self.setup_board(parameters)
        
        self.power_supply.enable_output(channel=1)
        self.power_supply.enable_output(channel=2)
        
        best_data = None
        best_quality = 0
        
        for attempt in range(max_retries):
            if attempt > 0:
                self.setup_oscilloscope(parameters)
                self.setup_board(parameters)
                time.sleep(0.05)
            
            self.oscilloscope.run_acquisition_block()
            time.sleep(0.02)
            self.board.run_pulses(number_repetitions=1)
            
            capture_duration = self.oscilloscope.number_samples * self.oscilloscope.sampling_time
            time.sleep(max(0.1, capture_duration * 2 + 0.1))
            
            data = self.oscilloscope.read_data()
            
            max_voltage = data["Input Voltage"].max()
            unique_currents = len(np.unique(data["Current"]))
            voltage_ok = max_voltage > voltage * 0.7
            current_ok = unique_currents > 20
            
            quality = (1 if voltage_ok else 0) + (1 if current_ok else 0) + unique_currents / 100
            
            if voltage_ok and current_ok:
                # Calculate inductance from DC-biased measurement
                # Skip the first pulse (DC buildup) and stabilization pulses
                # Analyze only the measurement portion
                inductance, peak_current, slopes = self.calculate_inductance_from_dc_bias_data(
                    data, voltage, dc_bias_current, parameters
                )
                
                if inductance is not None:
                    self.power_supply.disable_output(channel=1)
                    self.power_supply.disable_output(channel=2)
                    
                    # Calculate actual DC current from data
                    current = data["Current"].values
                    # Find the measurement region (after stabilization)
                    mid_point = len(current) // 2
                    actual_dc = np.mean(current[mid_point:])
                    actual_ripple = (np.max(current[mid_point:]) - np.min(current[mid_point:])) / 2
                    
                    return {
                        'data': data,
                        'inductance': inductance,
                        'peak_current': peak_current,
                        'dc_current': actual_dc,
                        'ac_ripple': actual_ripple,
                        'target_dc': dc_bias_current,
                        'frequency': frequency,
                        'voltage': voltage,
                        'slopes': slopes,
                        'attempts': attempt + 1
                    }
            
            if quality > best_quality:
                best_quality = quality
                best_data = data
            
            if attempt < max_retries - 1:
                if self.verbose:
                    print(f"  Retry {attempt + 1}: max_V={max_voltage:.2f}, unique_I={unique_currents}")
                time.sleep(0.1)
        
        self.power_supply.disable_output(channel=1)
        self.power_supply.disable_output(channel=2)
        
        if best_data is not None:
            return {'data': best_data, 'inductance': None, 'dc_current': None, 'failed': True}
        return None

    def calculate_inductance_from_dc_bias_data(self, data, voltage, dc_bias_current, parameters, smooth_current=True, smooth_window=7):
        """
        Calculate inductance from DC-biased TPT data.
        
        Skips the initial DC buildup pulse and analyzes the measurement pulses.
        """
        import numpy as np
        
        time_arr = data["time"].values
        current = data["Current"].values
        input_voltage = data["Input Voltage"].values
        
        # Apply smoothing to reduce noise
        if smooth_current:
            current = self.smooth_signal(current, smooth_window)
        
        # Find the measurement region - skip first pulse and stabilization
        # The first pulse is longer (t1), followed by stabilization cycles
        # Look for the region where current is oscillating around the DC bias level
        
        voltage_threshold = voltage * 0.5
        positive_regions = input_voltage > voltage_threshold
        
        # Find all rising edges
        transitions = []
        for i in range(1, len(positive_regions)):
            if positive_regions[i] and not positive_regions[i-1]:
                transitions.append(i)
        
        if len(transitions) < 4:
            return None, None, []
        
        # Skip first 3 transitions (first pulse + 2 stabilization cycles)
        # and analyze remaining measurement pulses
        measurement_transitions = transitions[3:]
        
        slopes = []
        peak_current = 0
        
        for j, start_idx in enumerate(measurement_transitions):
            # Find end of positive voltage region
            end_idx = start_idx
            while end_idx < len(positive_regions) - 1 and positive_regions[end_idx]:
                end_idx += 1
            
            if end_idx - start_idx < 10:
                continue
            
            # Extract segment (middle 60% to avoid edges)
            margin = int((end_idx - start_idx) * 0.2)
            seg_start = start_idx + margin
            seg_end = end_idx - margin
            
            if seg_end <= seg_start + 5:
                continue
            
            t_segment = time_arr[seg_start:seg_end]
            i_segment = current[seg_start:seg_end]
            v_segment = input_voltage[seg_start:seg_end]
            
            peak_current = max(peak_current, max(abs(i_segment)))
            
            avg_voltage = np.mean(v_segment)
            
            # Linear regression for slope
            n = len(t_segment)
            t_mean = np.mean(t_segment)
            i_mean = np.mean(i_segment)
            
            numerator = np.sum((t_segment - t_mean) * (i_segment - i_mean))
            denominator = np.sum((t_segment - t_mean) ** 2)
            
            if denominator > 0:
                slope = numerator / denominator
                if abs(slope) > 0.001:
                    pulse_inductance = abs(avg_voltage / slope)
                    slopes.append((slope, pulse_inductance, avg_voltage))
        
        if not slopes:
            return None, None, []
        
        # Average inductance from measurement pulses
        inductances = [s[1] for s in slopes]
        avg_inductance = sum(inductances) / len(inductances)
        
        if self.verbose and len(inductances) > 1:
            std = np.std(inductances)
            print(f"  DC-bias measurement: L={avg_inductance*1000:.2f}mH (std={std*1000:.2f}mH, n={len(inductances)})")
        
        return avg_inductance, peak_current, slopes

    def run_dc_bias_sweep(self, voltage, frequency, dc_currents, num_pulses=5, max_retries=3,
                          inductance_estimate=0.003, reference_inductance=None, plot=True, save_plot=True):
        """
        Run inductance measurement across multiple DC bias levels.
        
        This shows how inductance changes with DC bias - key for detecting saturation.
        
        Args:
            voltage: Test voltage in V
            frequency: Test frequency in Hz
            dc_currents: List of DC bias currents in A (e.g., [0.01, 0.05, 0.1, 0.2, 0.5])
            num_pulses: Pulses per measurement
            max_retries: Retries per measurement
            inductance_estimate: Initial inductance estimate (updated as we go)
            reference_inductance: Reference L for comparison
            plot: Show plot
            save_plot: Save plot to file
            
        Returns:
            dict with results
        """
        import matplotlib.pyplot as plt
        
        results = {
            'dc_currents': [],
            'inductances': [],
            'actual_dc_currents': [],
            'ac_ripples': [],
            'raw_results': []
        }
        
        print("=" * 60)
        print("INDUCTANCE VS DC BIAS SWEEP")
        print("=" * 60)
        print(f"Voltage: {voltage} V, Frequency: {frequency/1000:.0f} kHz")
        print(f"DC bias currents: {[I*1000 for I in dc_currents]} mA")
        print("=" * 60)
        
        L_estimate = inductance_estimate
        
        for dc_current in dc_currents:
            result = self.run_dc_bias_measurement(
                voltage=voltage,
                frequency=frequency,
                dc_bias_current=dc_current,
                num_pulses=num_pulses,
                max_retries=max_retries,
                inductance_estimate=L_estimate
            )
            
            if result and result.get('inductance'):
                L_mH = result['inductance'] * 1000
                dc_mA = result['dc_current'] * 1000
                results['dc_currents'].append(dc_current)
                results['inductances'].append(result['inductance'])
                results['actual_dc_currents'].append(result['dc_current'])
                results['ac_ripples'].append(result['ac_ripple'])
                results['raw_results'].append(result)
                
                # Update inductance estimate for next measurement
                L_estimate = result['inductance']
                
                print(f"I_dc={dc_current*1000:.0f}mA: L={L_mH:.2f}mH, actual_dc={dc_mA:.1f}mA")
            else:
                print(f"I_dc={dc_current*1000:.0f}mA: FAILED")
        
        if results['inductances']:
            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            
            L_max = max(results['inductances'])
            L_min = min(results['inductances'])
            L_drop = (L_max - L_min) / L_max * 100
            
            print(f"L range: {L_min*1000:.2f} - {L_max*1000:.2f} mH")
            print(f"L drop: {L_drop:.1f}%")
            
            if L_drop > 30:
                print("⚠️  Significant inductance drop detected - approaching saturation!")
            
            if plot or save_plot:
                fig, ax = plt.subplots(figsize=(10, 6))
                
                dc_mA = [I*1000 for I in results['dc_currents']]
                L_mH = [L*1000 for L in results['inductances']]
                
                ax.plot(dc_mA, L_mH, 'bo-', markersize=10, linewidth=2, label='Measured')
                
                if reference_inductance:
                    ax.axhline(y=reference_inductance*1000, color='r', linestyle='--',
                              linewidth=2, label=f'Reference ({reference_inductance*1000:.2f} mH)')
                
                ax.set_xlabel('DC Bias Current (mA)', fontsize=12)
                ax.set_ylabel('Inductance (mH)', fontsize=12)
                ax.set_title(f'Inductance vs DC Bias @ {voltage}V, {frequency/1000:.0f}kHz', fontsize=14)
                ax.grid(True, alpha=0.3)
                ax.legend()
                
                plt.tight_layout()
                
                if save_plot:
                    filename = f'inductance_dc_sweep_{voltage}V_{frequency/1000:.0f}kHz.png'
                    plt.savefig(filename, dpi=150)
                    print(f"Plot saved to {filename}")
                
                if plot:
                    plt.show()
                else:
                    plt.close()
        
        return results

    def run_test(self, measure_parameters):
        """
        Run inductance measurement with frequency sweep and saturation detection.
        
        Sweeps from high frequency to low frequency, measuring inductance at each point.
        Stops when saturation is detected or safety limits are reached.
        
        Args:
            measure_parameters: MeasureParameters instance
            
        Returns:
            MeasurementResult: Contains inductance vs frequency data and saturation info
        """
        result = self.MeasurementResult()
        
        # Generate frequency sweep (logarithmic spacing from high to low)
        import numpy as np
        frequencies = np.logspace(
            np.log10(measure_parameters.start_frequency),
            np.log10(measure_parameters.min_frequency),
            measure_parameters.frequency_steps
        )
        
        voltage = measure_parameters.start_voltage
        
        # Get core parameters
        core_params = self.CORE_DATABASE.get(measure_parameters.core_type, {})
        material_params = self.MATERIAL_DATABASE.get(measure_parameters.material, {})
        
        effective_area = core_params.get('effective_area', 100e-6)
        effective_length = core_params.get('effective_length', 50e-3)
        mu_r = material_params.get('initial_permeability', 2000)
        B_sat = material_params.get('saturation_flux_density', 0.4)
        N = measure_parameters.number_turns
        
        # Calculate theoretical inductance (ungapped)
        mu_0 = 4 * math.pi * 1e-7
        if measure_parameters.air_gap == 0:
            theoretical_L = mu_0 * mu_r * N**2 * effective_area / effective_length
        else:
            # With air gap: L ≈ μ0 * N² * Ae / gap (gap dominates)
            reluctance_gap = measure_parameters.air_gap / (mu_0 * effective_area)
            reluctance_core = effective_length / (mu_0 * mu_r * effective_area)
            theoretical_L = N**2 / (reluctance_gap + reluctance_core)
        
        result.theoretical_inductance = theoretical_L
        
        print("=" * 60)
        print("INDUCTANCE MEASUREMENT WITH SATURATION DETECTION")
        print("=" * 60)
        print(f"Core: {measure_parameters.core_type} ({measure_parameters.material})")
        print(f"Turns: {N}, Air gap: {measure_parameters.air_gap*1000:.2f} mm")
        print(f"Effective Area: {effective_area*1e6:.1f} mm², Length: {effective_length*1e3:.1f} mm")
        print(f"Theoretical inductance: {theoretical_L*1e3:.2f} mH")
        print(f"Material Bsat: {B_sat*1000:.0f} mT")
        print("-" * 60)
        print(f"Test voltage: {voltage} V")
        print(f"Frequency sweep: {measure_parameters.start_frequency/1000:.1f} kHz -> {measure_parameters.min_frequency/1000:.1f} kHz")
        print(f"Max flux density limit: {measure_parameters.max_flux_density*1000:.0f} mT")
        print(f"Max current limit: {measure_parameters.max_current} A")
        print("=" * 60)
        
        for i, frequency in enumerate(frequencies):
            if self.verbose:
                print(f"\n[{i+1}/{len(frequencies)}] Testing at {frequency/1000:.2f} kHz...")
            
            try:
                # Run measurement
                data = self.run_single_measurement(
                    voltage, 
                    frequency, 
                    measure_parameters.num_pulses
                )
                
                # Save raw data
                data.to_csv(f"inductance_measurement_{i}_{frequency:.0f}Hz.csv")
                
                # Calculate inductance from current slope
                inductance, peak_current, slopes = self.calculate_inductance_from_slope(data, voltage)
                
                if inductance is None:
                    print(f"  Warning: Could not calculate inductance at {frequency/1000:.2f} kHz")
                    continue
                
                # Calculate flux density: B = L * I / (N * Ae)
                flux_density = inductance * peak_current / (N * effective_area)
                
                result.add_point(frequency, inductance, peak_current, flux_density)
                
                if self.verbose:
                    print(f"  Inductance: {inductance*1e3:.3f} mH")
                    print(f"  Peak current: {peak_current:.3f} A")
                    print(f"  Flux density: {flux_density*1000:.1f} mT")
                    if len(slopes) > 0:
                        print(f"  dI/dt: {slopes[0]:.1f} A/s")
                
                # Plot if enabled
                if self.plot_each_measurement:
                    plt.figure(figsize=(12, 4))
                    plt.subplot(1, 2, 1)
                    plt.plot(data["time"]*1e6, data["Input Voltage"], label="Voltage")
                    plt.xlabel("Time (µs)")
                    plt.ylabel("Voltage (V)")
                    plt.legend()
                    plt.title(f"f={frequency/1000:.1f}kHz")
                    
                    plt.subplot(1, 2, 2)
                    plt.plot(data["time"]*1e6, data["Current"], label="Current")
                    plt.xlabel("Time (µs)")
                    plt.ylabel("Current (A)")
                    plt.legend()
                    plt.tight_layout()
                    plt.show()
                
                # Safety check: max flux density
                if flux_density > measure_parameters.max_flux_density:
                    print(f"\n⚠️  FLUX LIMIT: B = {flux_density*1000:.1f} mT exceeded limit ({measure_parameters.max_flux_density*1000:.0f} mT)")
                    result.saturation_detected = True
                    result.saturation_frequency = frequency
                    break
                
                # Safety check: max current
                if peak_current > measure_parameters.max_current:
                    print(f"\n⚠️  SAFETY STOP: Peak current ({peak_current:.2f} A) exceeded limit ({measure_parameters.max_current} A)")
                    result.saturation_detected = True
                    result.saturation_frequency = frequency
                    break
                
                # Check for ADC clipping (current approaching scope range limit)
                # current_peak in calculate_test_parameters sets the scope range
                current_range = 0.2  # Must match current_peak in calculate_test_parameters
                if peak_current > current_range * 0.9:
                    print(f"\n⚠️  ADC CLIPPING: Peak current ({peak_current*1000:.1f} mA) approaching scope range ({current_range*1000:.0f} mA)")
                    print(f"   Data beyond this point would be invalid.")
                    break
                
                # Check for saturation (inductance drop)
                if self.detect_saturation(result, measure_parameters.saturation_threshold):
                    print(f"\n⚠️  SATURATION DETECTED at {frequency/1000:.2f} kHz")
                    print(f"   Nominal inductance: {result.nominal_inductance*1e3:.3f} mH")
                    print(f"   Current inductance: {inductance*1e3:.3f} mH")
                    print(f"   Drop: {(1 - inductance/result.nominal_inductance)*100:.1f}%")
                    print(f"   Flux density: {flux_density*1000:.1f} mT")
                    result.saturation_detected = True
                    result.saturation_frequency = frequency
                    break
                    
            except Exception as e:
                print(f"  Error at {frequency/1000:.2f} kHz: {e}")
                continue
        
        # Ensure outputs are disabled
        self.power_supply.disable_output(channel=1)
        self.power_supply.disable_output(channel=2)
        
        # Print summary
        print("\n" + "=" * 60)
        print("MEASUREMENT COMPLETE")
        print("=" * 60)
        print(f"Theoretical inductance: {theoretical_L*1e3:.2f} mH")
        
        if result.nominal_inductance:
            print(f"Measured inductance: {result.nominal_inductance*1e3:.3f} mH")
            print(f"Ratio (meas/theo): {result.nominal_inductance/theoretical_L*100:.1f}%")
        elif result.inductances:
            avg_inductance = sum(result.inductances) / len(result.inductances)
            print(f"Average inductance: {avg_inductance*1e3:.3f} mH")
        
        if result.saturation_detected:
            print(f"Saturation detected at: {result.saturation_frequency/1000:.2f} kHz")
            if result.flux_densities:
                print(f"Max flux density reached: {max(result.flux_densities)*1000:.1f} mT")
        else:
            print("No saturation detected in frequency range")
        
        print(f"Measurements taken: {len(result.inductances)}")
        
        # Plot summary
        if result.inductances:
            fig, axes = plt.subplots(1, 3, figsize=(15, 5))
            
            # Inductance vs Frequency
            axes[0].semilogx(result.frequencies, [L*1e3 for L in result.inductances], 'b-o')
            axes[0].axhline(theoretical_L*1e3, color='g', linestyle='--', alpha=0.7, label=f'Theoretical: {theoretical_L*1e3:.2f} mH')
            axes[0].set_xlabel("Frequency (Hz)")
            axes[0].set_ylabel("Inductance (mH)")
            axes[0].set_title("Inductance vs Frequency")
            axes[0].grid(True)
            axes[0].invert_xaxis()
            axes[0].legend()
            
            if result.saturation_detected:
                axes[0].axvline(result.saturation_frequency, color='r', linestyle='--', alpha=0.5)
            
            # Peak Current vs Frequency
            axes[1].semilogx(result.frequencies, result.peak_currents, 'r-o')
            axes[1].set_xlabel("Frequency (Hz)")
            axes[1].set_ylabel("Peak Current (A)")
            axes[1].set_title("Peak Current vs Frequency")
            axes[1].grid(True)
            axes[1].invert_xaxis()
            
            # Flux Density vs Frequency
            axes[2].semilogx(result.frequencies, [B*1000 for B in result.flux_densities], 'm-o')
            axes[2].axhline(B_sat*1000, color='r', linestyle='--', alpha=0.7, label=f'Bsat: {B_sat*1000:.0f} mT')
            axes[2].axhline(measure_parameters.max_flux_density*1000, color='orange', linestyle='--', alpha=0.7, label=f'Limit: {measure_parameters.max_flux_density*1000:.0f} mT')
            axes[2].set_xlabel("Frequency (Hz)")
            axes[2].set_ylabel("Flux Density (mT)")
            axes[2].set_title("Flux Density vs Frequency")
            axes[2].grid(True)
            axes[2].invert_xaxis()
            axes[2].legend()
            
            plt.tight_layout()
            plt.savefig("inductance_measurement_summary.png", dpi=150)
            plt.show()
        
        # Save results
        df = result.to_dataframe()
        df.to_csv("inductance_measurement_results.csv", index=False)
        print(f"\nResults saved to inductance_measurement_results.csv")
        
        return result

    # =========================================================================
    # CORE LOSS MEASUREMENT (TPT IECON 2020 Paper Method)
    # =========================================================================
    # 
    # Reference: "Triple Pulse Test (TPT) for Characterizing Power Loss in 
    #            Magnetic Components" - IECON 2020
    #
    # Core loss is calculated by integrating V×I over a complete B-H loop:
    #     E_core = ∫(V(t) × I(t)) dt  for one complete cycle
    #     P_core = E_core × f_switching
    #
    # For accurate measurement, the B-H loop must be CLOSED, requiring:
    #     ∫V dt (positive) = ∫V dt (negative)  (volt-second balance)
    #
    # If flux is not balanced, reactive energy is incorrectly counted as loss.
    # The "flux closure error" metric checks this:
    #     flux_error = |λ_final| / (λ_max - λ_min) × 100%
    #
    # Target: flux_error < 5% for accurate loss measurement
    # =========================================================================

    class CoreLossParameters:
        """
        Parameters for core loss measurement calculated from magnetic info.
        
        MAGNETIC RELATIONSHIPS
        ----------------------
        Flux linkage:     λ = N × Φ = N × B × Ae
        Voltage:          V = dλ/dt = N × Ae × dB/dt
        
        For a rectangular pulse with duration t:
            V × t = N × Ae × ΔB
            
        Therefore:
            ΔB = V × t / (N × Ae)
            
        Or solving for voltage given desired ΔB:
            V = ΔB × N × Ae / t
            
        Current (for ungapped core):
            I = B × le / (μ₀ × μr × N)
            
        Inductance (ungapped):
            L = μ₀ × μr × N² × Ae / le
        """
        
        def __init__(self, 
                     core_type='RM10',
                     material='N87',
                     number_turns=26,
                     air_gap=0,
                     frequency=100000,
                     flux_density_pp=0.1,  # Peak-to-peak flux density in T
                     dc_bias_flux=0,       # DC bias flux density in T
                     v_positive_measured=6.4,   # Measured V+ for half-bridge
                     v_negative_measured=-0.7): # Measured V- (body diode)
            """
            Initialize core loss parameters.
            
            Args:
                core_type: Core geometry from CORE_DATABASE ('RM10', 'RM8', 'RM12')
                material: Core material from MATERIAL_DATABASE ('N87', 'N97', 'N49')
                number_turns: Number of winding turns
                air_gap: Air gap in meters (0 for ungapped)
                frequency: Switching frequency in Hz
                flux_density_pp: Desired peak-to-peak AC flux density in Tesla
                dc_bias_flux: DC bias flux density in Tesla
                v_positive_measured: Measured positive voltage during switch-on
                v_negative_measured: Measured negative voltage during freewheel
            """
            self.core_type = core_type
            self.material = material
            self.number_turns = number_turns
            self.air_gap = air_gap
            self.frequency = frequency
            self.flux_density_pp = flux_density_pp
            self.dc_bias_flux = dc_bias_flux
            self.v_positive_measured = v_positive_measured
            self.v_negative_measured = v_negative_measured
            
            # These will be calculated
            self.effective_area = None
            self.effective_length = None
            self.effective_volume = None
            self.permeability = None
            self.saturation_flux = None
            self.inductance = None
            self.t_positive = None
            self.t_negative = None
            self.peak_current = None
            self.volt_seconds_required = None

    def calculate_core_loss_parameters(self, params):
        """
        Calculate TPT parameters from magnetic core information.
        
        THEORY
        ------
        For core loss measurement, we need to:
        1. Apply a specific AC flux density swing (B_pp)
        2. Achieve volt-second balance for closed B-H loop
        
        Given the asymmetric half-bridge voltages:
            V+ = v_positive_measured (e.g., 6.4V)
            V- = v_negative_measured (e.g., -0.7V)
            
        For volt-second balance:
            V+ × t+ = |V-| × t-
            
        For the desired flux swing:
            V+ × t+ = N × Ae × (B_pp / 2)  (half the p-p swing in positive phase)
            
        Solving:
            t+ = N × Ae × (B_pp / 2) / V+
            t- = V+ × t+ / |V-|
            
        The period T = t+ + t- determines the actual frequency.
        
        If the desired frequency is fixed, we may need to adjust voltage or
        accept a different B_pp.
        
        Args:
            params: CoreLossParameters object with magnetic info
            
        Returns:
            CoreLossParameters: Updated with calculated timing and electrical values
        """
        import math
        
        # Physical constants
        MU_0 = 4 * math.pi * 1e-7  # H/m
        
        # Look up core properties
        if params.core_type not in self.CORE_DATABASE:
            raise ValueError(f"Unknown core type: {params.core_type}. "
                           f"Available: {list(self.CORE_DATABASE.keys())}")
        
        core = self.CORE_DATABASE[params.core_type]
        params.effective_area = core['effective_area']
        params.effective_length = core['effective_length']
        params.effective_volume = core['effective_volume']
        
        # Look up material properties
        if params.material not in self.MATERIAL_DATABASE:
            raise ValueError(f"Unknown material: {params.material}. "
                           f"Available: {list(self.MATERIAL_DATABASE.keys())}")
        
        material = self.MATERIAL_DATABASE[params.material]
        params.permeability = material['initial_permeability']
        params.saturation_flux = material['saturation_flux_density']
        
        N = params.number_turns
        Ae = params.effective_area
        le = params.effective_length
        mu_r = params.permeability
        B_pp = params.flux_density_pp
        V_pos = params.v_positive_measured
        V_neg = abs(params.v_negative_measured)
        
        # Calculate inductance (ungapped)
        if params.air_gap == 0:
            params.inductance = MU_0 * mu_r * N**2 * Ae / le
        else:
            # With air gap, effective permeability is reduced
            # μ_eff ≈ le / (le/μr + g)  where g is gap length
            g = params.air_gap
            mu_eff = le / (le / mu_r + g)
            params.inductance = MU_0 * mu_eff * N**2 * Ae / le
        
        # Calculate volt-seconds needed for half the B swing (one direction)
        # λ = N × Ae × B, so Δλ = N × Ae × ΔB
        # For p-p swing, each half-period sees B_pp/2
        volt_seconds_half = N * Ae * (B_pp / 2)
        params.volt_seconds_required = volt_seconds_half
        
        # Calculate timing for volt-second balance
        # V+ × t+ = volt_seconds_half
        # V- × t- = volt_seconds_half (for balance)
        params.t_positive = volt_seconds_half / V_pos
        params.t_negative = volt_seconds_half / V_neg
        
        T_period = params.t_positive + params.t_negative
        actual_frequency = 1.0 / T_period
        
        # Calculate peak current
        # I = B × le / (μ₀ × μr × N)  for ungapped
        B_peak = B_pp / 2 + params.dc_bias_flux
        if params.air_gap == 0:
            params.peak_current = B_peak * le / (MU_0 * mu_r * N)
        else:
            # With gap, use actual inductance
            # I = λ / L = N × Ae × B / L
            params.peak_current = N * Ae * B_peak / params.inductance
        
        # Print summary
        print("=" * 60)
        print("CORE LOSS PARAMETER CALCULATION")
        print("=" * 60)
        print(f"Core: {params.core_type} ({params.material})")
        print(f"  Ae = {Ae*1e6:.1f} mm²")
        print(f"  le = {le*1e3:.1f} mm")
        print(f"  Ve = {params.effective_volume*1e9:.1f} mm³")
        print(f"  μr = {mu_r}")
        print(f"  Bsat = {params.saturation_flux*1000:.0f} mT")
        print(f"\nWinding: N = {N} turns, gap = {params.air_gap*1e3:.2f} mm")
        print(f"  Calculated L = {params.inductance*1e3:.2f} mH")
        print(f"\nOperating Point:")
        print(f"  Desired B_pp = {B_pp*1000:.1f} mT")
        print(f"  DC bias = {params.dc_bias_flux*1000:.1f} mT")
        print(f"  B_peak = {B_peak*1000:.1f} mT ({B_peak/params.saturation_flux*100:.0f}% of Bsat)")
        print(f"\nHalf-Bridge Voltages:")
        print(f"  V+ = {V_pos:.2f} V, V- = {-V_neg:.2f} V")
        print(f"  Ratio V+/|V-| = {V_pos/V_neg:.1f}")
        print(f"\nCalculated Timing (for flux balance):")
        print(f"  t+ = {params.t_positive*1e6:.2f} µs")
        print(f"  t- = {params.t_negative*1e6:.2f} µs")
        print(f"  T = {T_period*1e6:.2f} µs")
        print(f"  Actual frequency = {actual_frequency/1000:.1f} kHz")
        print(f"  (Requested: {params.frequency/1000:.1f} kHz)")
        print(f"\nElectrical Parameters:")
        print(f"  Volt-seconds (half-cycle) = {volt_seconds_half*1e6:.3f} µVs")
        print(f"  Expected I_peak = {params.peak_current*1000:.1f} mA")
        print("=" * 60)
        
        # Warn if flux density is high
        if B_peak > 0.8 * params.saturation_flux:
            print(f"\n⚠️  WARNING: B_peak = {B_peak*1000:.0f} mT is close to saturation!")
            print(f"   Consider reducing flux_density_pp or dc_bias_flux")
        
        # Note about frequency mismatch
        if abs(actual_frequency - params.frequency) / params.frequency > 0.1:
            print(f"\n📌 NOTE: Actual frequency ({actual_frequency/1000:.1f} kHz) differs from")
            print(f"   requested ({params.frequency/1000:.1f} kHz) due to volt-second balance constraint.")
            print(f"   The half-bridge voltage ratio determines the duty cycle.")
        
        return params

    def measure_core_loss_from_params(self, params, num_pulses=50, plot=True, save_plot=True):
        """
        Measure core loss using parameters calculated from magnetic info.
        
        This is a convenience method that:
        1. Calculates timing from magnetic parameters
        2. Runs the core loss measurement
        3. Reports results with magnetic context
        
        Args:
            params: CoreLossParameters (will be updated with calculated values)
            num_pulses: Number of pulses to apply
            plot: Whether to display plots
            save_plot: Whether to save plots
            
        Returns:
            CoreLossResult with measurement data
        """
        # Calculate parameters if not already done
        if params.t_positive is None:
            params = self.calculate_core_loss_parameters(params)
        
        # Get supply voltage (use positive rail setting)
        # Note: The actual voltages are asymmetric due to half-bridge
        voltage = params.v_positive_measured + 0.6  # Approximate supply voltage
        
        print(f"\n🔬 Running measurement with calculated parameters...")
        print(f"   t+ = {params.t_positive*1e6:.2f} µs, t- = {params.t_negative*1e6:.2f} µs")
        
        # Run measurement
        result = self.measure_core_loss(
            voltage=5.0,  # Supply voltage setting (will measure actual)
            t_positive=params.t_positive,
            t_negative=params.t_negative,
            num_pulses=num_pulses,
            plot=plot,
            save_plot=save_plot
        )
        
        # Add magnetic context to result
        if result.power_watts is not None:
            # Calculate volumetric power loss (W/m³) and specific loss (mW/cm³)
            P_volumetric = result.power_watts / params.effective_volume
            P_specific = P_volumetric / 1000  # mW/cm³ = kW/m³
            
            T_period = params.t_positive + params.t_negative
            actual_freq = 1.0 / T_period
            
            print("\n" + "=" * 60)
            print("MAGNETIC CONTEXT")
            print("=" * 60)
            print(f"Core: {params.core_type} {params.material}, N = {params.number_turns}")
            print(f"Target B_pp: {params.flux_density_pp*1000:.1f} mT")
            print(f"Frequency: {actual_freq/1000:.1f} kHz")
            print(f"\nCore Loss Results:")
            print(f"  Total power: {result.power_watts*1000:.2f} mW")
            print(f"  Volumetric: {P_volumetric/1000:.1f} kW/m³ = {P_specific:.1f} mW/cm³")
            print(f"  Per cycle: {result.energy_per_cycle_joules*1e6:.3f} µJ")
            
            # Compare with Steinmetz estimation if possible
            # P = k × f^α × B^β (typical α ≈ 1.5, β ≈ 2.5 for ferrites)
            # N87 at 100kHz, 100mT: ~100 mW/cm³ (from datasheet)
            # Scale roughly: P ∝ f^1.5 × B^2.5
            B_mT = params.flux_density_pp * 1000 / 2  # Peak (not p-p)
            f_kHz = actual_freq / 1000
            # Reference: N87 at 100kHz, 100mT ≈ 100 mW/cm³
            P_steinmetz_ref = 100  # mW/cm³ at 100kHz, 100mT
            P_steinmetz_est = P_steinmetz_ref * (f_kHz/100)**1.5 * (B_mT/100)**2.5
            P_steinmetz_total = P_steinmetz_est * params.effective_volume * 1e6  # mW
            
            print(f"\nSteinmetz Estimate (N87 approximation):")
            print(f"  ~{P_steinmetz_est:.1f} mW/cm³ → {P_steinmetz_total:.2f} mW total")
            print(f"  Measured/Estimated ratio: {result.power_watts*1000/P_steinmetz_total:.2f}")
            
            if result.flux_error_percent > 5:
                print(f"\n⚠️  Flux error ({result.flux_error_percent:.1f}%) may inflate measured loss")
            print("=" * 60)
        
        return result

    class CoreLossResult:
        """Container for core loss measurement results."""
        def __init__(self):
            self.power_watts = None
            self.energy_per_cycle_joules = None
            self.frequency_hz = None
            self.flux_error_percent = None
            self.cycles_analyzed = 0
            self.t_positive_us = None
            self.t_negative_us = None
            self.voltage_positive = None
            self.voltage_negative = None
            self.peak_current = None
            self.peak_flux_wb = None
            self.raw_data = None
            self.energies_per_cycle = []
            self.flux_errors_per_cycle = []
            
        def __repr__(self):
            return (f"CoreLossResult(P={self.power_watts*1000:.2f}mW @ {self.frequency_hz/1000:.1f}kHz, "
                    f"flux_err={self.flux_error_percent:.1f}%)")
        
        def to_dict(self):
            return {
                'power_watts': self.power_watts,
                'power_mW': self.power_watts * 1000 if self.power_watts else None,
                'energy_per_cycle_uJ': self.energy_per_cycle_joules * 1e6 if self.energy_per_cycle_joules else None,
                'frequency_kHz': self.frequency_hz / 1000 if self.frequency_hz else None,
                'flux_error_percent': self.flux_error_percent,
                'cycles_analyzed': self.cycles_analyzed,
                't_positive_us': self.t_positive_us,
                't_negative_us': self.t_negative_us,
                'V_positive': self.voltage_positive,
                'V_negative': self.voltage_negative,
                'peak_current_A': self.peak_current,
            }

    def find_optimal_timing_for_flux_balance(self, voltage, t_total=10e-6, num_pulses=50,
                                              t_pos_range=(0.5e-6, 2.0e-6), num_steps=10):
        """
        Sweep t_positive to find timing that minimizes flux closure error.
        
        BACKGROUND
        ----------
        In a half-bridge topology with body diode freewheeling:
            - V+ ≈ supply voltage (e.g., 6.4V)
            - V- ≈ -0.7V (body diode drop)
        
        For volt-second balance: V+ × t+ = |V-| × t-
        
        This method sweeps t+ to find the timing that achieves minimum flux error.
        
        Args:
            voltage: Supply voltage in V
            t_total: Total period (t_positive + t_negative) in seconds
            num_pulses: Number of pulses to apply
            t_pos_range: Tuple of (min, max) t_positive to sweep in seconds
            num_steps: Number of timing steps to try
            
        Returns:
            dict: Contains optimal timing and sweep results
        """
        import numpy as np
        
        print("=" * 60)
        print("OPTIMAL TIMING SEARCH FOR VOLT-SECOND BALANCE")
        print("=" * 60)
        print(f"Period: {t_total*1e6:.1f} µs ({1/t_total/1000:.1f} kHz)")
        print(f"Sweeping t_pos: {t_pos_range[0]*1e6:.1f} - {t_pos_range[1]*1e6:.1f} µs")
        print("=" * 60)
        
        t_pos_values = np.linspace(t_pos_range[0], t_pos_range[1], num_steps)
        results = []
        
        for t_pos in t_pos_values:
            t_neg = t_total - t_pos
            
            # Create pulse train with this timing
            pulses_periods = []
            for _ in range(num_pulses):
                pulses_periods.append(t_pos)
                pulses_periods.append(t_neg)
            
            parameters = self.TestParameters(
                positive_voltage_peak=voltage,
                negative_voltage_peak=voltage,
                current_peak=2.0,  # Generous range
                pulses_periods=pulses_periods,
                steady_period=t_pos
            )
            
            # Setup hardware
            if not self._psu_initialized or self._last_voltage != voltage:
                self.setup_power_supply(parameters, startup=not self._psu_initialized)
                self._last_voltage = voltage
                self._psu_initialized = True
            
            self.setup_oscilloscope(parameters)
            self.setup_board(parameters)
            
            self.power_supply.enable_output(channel=1)
            self.power_supply.enable_output(channel=2)
            
            time.sleep(0.02)
            self.oscilloscope.run_acquisition_block()
            time.sleep(0.02)
            self.board.run_pulses(number_repetitions=1)
            time.sleep(0.15)
            
            data = self.oscilloscope.read_data()
            
            self.power_supply.disable_output(channel=1)
            self.power_supply.disable_output(channel=2)
            
            # Analyze flux closure
            time_arr = data["time"].values
            voltage_arr = data["Input Voltage"].values
            dt = time_arr[1] - time_arr[0]
            
            flux = np.cumsum(voltage_arr) * dt
            flux_range = np.max(flux) - np.min(flux)
            
            # Find steady-state cycles (skip first 10, last 5)
            threshold = (np.max(voltage_arr) + np.min(voltage_arr)) / 2
            rising_edges = np.where((voltage_arr[:-1] < threshold) & (voltage_arr[1:] > threshold))[0]
            
            if len(rising_edges) > 15:
                steady_edges = rising_edges[10:-5]
                flux_errors = []
                for i in range(len(steady_edges) - 1):
                    start_idx = steady_edges[i]
                    end_idx = steady_edges[i + 1]
                    flux_cycle = flux[start_idx:end_idx]
                    cycle_range = np.max(flux_cycle) - np.min(flux_cycle)
                    if cycle_range > 0:
                        err = abs(flux_cycle[-1] - flux_cycle[0]) / cycle_range * 100
                        flux_errors.append(err)
                
                if flux_errors:
                    mean_flux_error = np.mean(flux_errors)
                    results.append({
                        't_pos': t_pos,
                        't_neg': t_neg,
                        'flux_error': mean_flux_error,
                        'data': data
                    })
                    print(f"  t+ = {t_pos*1e6:.2f} µs, t- = {t_neg*1e6:.2f} µs → flux error = {mean_flux_error:.1f}%")
        
        if not results:
            print("ERROR: No valid measurements")
            return None
        
        # Find optimal
        best = min(results, key=lambda x: x['flux_error'])
        print("\n" + "=" * 60)
        print(f"OPTIMAL: t+ = {best['t_pos']*1e6:.2f} µs, t- = {best['t_neg']*1e6:.2f} µs")
        print(f"         Flux error = {best['flux_error']:.1f}%")
        print("=" * 60)
        
        return {
            'optimal_t_pos': best['t_pos'],
            'optimal_t_neg': best['t_neg'],
            'min_flux_error': best['flux_error'],
            'sweep_results': results,
            'best_data': best['data']
        }

    def measure_core_loss(self, voltage, t_positive=0.9e-6, t_negative=9.1e-6, 
                          num_pulses=50, num_steady_cycles=35,
                          skip_first=10, skip_last=5,
                          auto_optimize_timing=False, plot=True, save_plot=True):
        """
        Measure core losses using the TPT method (IECON 2020 paper).
        
        METHODOLOGY
        -----------
        Core loss is the energy dissipated per cycle in the magnetic core:
        
            E_core = ∫ V(t) × I(t) dt  (integrated over one closed B-H loop)
            P_core = E_core × f_switching
        
        For accurate measurement, the B-H loop must be CLOSED (flux returns to
        starting point). This requires volt-second balance:
        
            V+ × t+ = |V-| × t-
        
        HALF-BRIDGE LIMITATION
        ----------------------
        In half-bridge with body diode freewheeling:
            V+ ≈ 6.4V (supply minus switch drop)
            V- ≈ -0.7V (body diode)
        
        The voltage ratio is ~9:1, so timing must be adjusted:
            t+ / t- ≈ 0.7 / 6.4 ≈ 0.11
        
        For 100kHz (10µs period): t+ ≈ 1µs, t- ≈ 9µs
        
        Even with optimal timing, flux error may not reach <5% due to
        diode voltage variability. Accept flux error with caveat.
        
        Args:
            voltage: Supply voltage in V (CH1 and CH2)
            t_positive: Duration of positive voltage pulse in seconds
            t_negative: Duration of negative voltage pulse in seconds
            num_pulses: Total number of complete cycles to apply
            num_steady_cycles: Number of steady-state cycles to analyze
            skip_first: Number of initial cycles to skip (transient)
            skip_last: Number of final cycles to skip
            auto_optimize_timing: If True, run timing sweep first
            plot: Whether to display plots
            save_plot: Whether to save plots to files
            
        Returns:
            CoreLossResult: Object containing power loss and measurement details
        """
        import numpy as np
        import matplotlib.pyplot as plt
        
        result = self.CoreLossResult()
        
        # Auto-optimize timing if requested
        if auto_optimize_timing:
            t_total = t_positive + t_negative
            opt_result = self.find_optimal_timing_for_flux_balance(
                voltage, t_total=t_total, num_pulses=30,
                t_pos_range=(t_total * 0.05, t_total * 0.20), num_steps=8
            )
            if opt_result:
                t_positive = opt_result['optimal_t_pos']
                t_negative = opt_result['optimal_t_neg']
                print(f"\nUsing optimized timing: t+ = {t_positive*1e6:.2f} µs, t- = {t_negative*1e6:.2f} µs")
        
        T_cycle = t_positive + t_negative
        frequency = 1.0 / T_cycle
        result.frequency_hz = frequency
        result.t_positive_us = t_positive * 1e6
        result.t_negative_us = t_negative * 1e6
        
        print("\n" + "=" * 60)
        print("CORE LOSS MEASUREMENT (TPT Method)")
        print("=" * 60)
        print(f"Voltage: {voltage} V")
        print(f"Timing: t+ = {t_positive*1e6:.2f} µs, t- = {t_negative*1e6:.2f} µs")
        print(f"Period: {T_cycle*1e6:.2f} µs ({frequency/1000:.1f} kHz)")
        print(f"Pulses: {num_pulses} total, analyzing cycles {skip_first+1} to {num_pulses-skip_last}")
        print("=" * 60)
        
        # Create pulse train
        pulses_periods = []
        for _ in range(num_pulses):
            pulses_periods.append(t_positive)
            pulses_periods.append(t_negative)
        
        parameters = self.TestParameters(
            positive_voltage_peak=voltage,
            negative_voltage_peak=voltage,
            current_peak=2.0,
            pulses_periods=pulses_periods,
            steady_period=t_positive
        )
        
        # Setup hardware
        if not self._psu_initialized or self._last_voltage != voltage:
            self.setup_power_supply(parameters, startup=not self._psu_initialized)
            self._last_voltage = voltage
            self._psu_initialized = True
        
        self.setup_oscilloscope(parameters)
        self.setup_board(parameters)
        
        self.power_supply.enable_output(channel=1)
        self.power_supply.enable_output(channel=2)
        
        time.sleep(0.02)
        self.oscilloscope.run_acquisition_block()
        time.sleep(0.02)
        self.board.run_pulses(number_repetitions=1)
        
        # Wait for capture
        capture_time = self.oscilloscope.number_samples * self.oscilloscope.sampling_time
        time.sleep(max(0.15, capture_time * 2))
        
        data = self.oscilloscope.read_data()
        result.raw_data = data
        
        self.power_supply.disable_output(channel=1)
        self.power_supply.disable_output(channel=2)
        
        # Extract waveforms
        time_arr = data["time"].values
        voltage_arr = data["Input Voltage"].values
        current_arr = data["Current"].values
        dt = time_arr[1] - time_arr[0]
        
        result.peak_current = np.max(np.abs(current_arr))
        
        # Measure actual voltages
        v_threshold = (np.max(voltage_arr) + np.min(voltage_arr)) / 2
        v_pos_samples = voltage_arr[voltage_arr > v_threshold]
        v_neg_samples = voltage_arr[voltage_arr < v_threshold]
        result.voltage_positive = np.mean(v_pos_samples) if len(v_pos_samples) > 0 else None
        result.voltage_negative = np.mean(v_neg_samples) if len(v_neg_samples) > 0 else None
        
        print(f"\nMeasured voltages: V+ = {result.voltage_positive:.2f} V, V- = {result.voltage_negative:.2f} V")
        
        # Calculate flux (volt-seconds)
        flux = np.cumsum(voltage_arr) * dt
        result.peak_flux_wb = (np.max(flux) - np.min(flux)) / 2
        
        # Find cycle boundaries (rising edges of voltage)
        rising_edges = np.where((voltage_arr[:-1] < v_threshold) & (voltage_arr[1:] > v_threshold))[0]
        
        if len(rising_edges) < skip_first + skip_last + 3:
            print(f"ERROR: Not enough cycles found ({len(rising_edges)} edges)")
            return result
        
        # Analyze steady-state cycles
        analysis_start = skip_first
        analysis_end = len(rising_edges) - skip_last - 1
        
        energies = []
        flux_errors = []
        
        for i in range(analysis_start, analysis_end):
            start_idx = rising_edges[i]
            end_idx = rising_edges[i + 1]
            
            v_cycle = voltage_arr[start_idx:end_idx]
            i_cycle = current_arr[start_idx:end_idx]
            t_cycle = time_arr[start_idx:end_idx]
            
            # Calculate energy: E = ∫V×I dt
            power_cycle = v_cycle * i_cycle
            energy = np.trapz(power_cycle, t_cycle)
            energies.append(energy)
            
            # Calculate flux closure error
            flux_cycle = np.cumsum(v_cycle) * dt
            flux_range = np.max(flux_cycle) - np.min(flux_cycle)
            if flux_range > 0:
                flux_err = abs(flux_cycle[-1] - flux_cycle[0]) / flux_range * 100
                flux_errors.append(flux_err)
        
        result.energies_per_cycle = energies
        result.flux_errors_per_cycle = flux_errors
        result.cycles_analyzed = len(energies)
        
        if energies:
            result.energy_per_cycle_joules = np.mean(energies)
            result.power_watts = result.energy_per_cycle_joules * frequency
            
        if flux_errors:
            result.flux_error_percent = np.mean(flux_errors)
        
        # Print results
        print("\n" + "-" * 40)
        print("RESULTS")
        print("-" * 40)
        print(f"Cycles analyzed: {result.cycles_analyzed}")
        print(f"Energy per cycle: {result.energy_per_cycle_joules*1e6:.3f} µJ")
        print(f"Core loss power: {result.power_watts*1000:.2f} mW")
        print(f"Flux closure error: {result.flux_error_percent:.1f}%")
        print(f"Peak current: {result.peak_current*1000:.1f} mA")
        
        # Warning if flux error is high
        if result.flux_error_percent > 5:
            print("\n⚠️  WARNING: Flux error > 5%")
            print("   The B-H loop is not fully closed. Power measurement includes")
            print("   reactive energy which inflates the apparent loss.")
            print("   Consider adjusting timing or using full-bridge topology.")
        
        if result.flux_error_percent > 20:
            print("\n❌ CAUTION: Flux error > 20%")
            print("   Measurement accuracy is significantly compromised.")
        
        print("-" * 40)
        
        # Plot results
        if plot or save_plot:
            fig, axes = plt.subplots(2, 2, figsize=(14, 10))
            
            # Full waveform
            ax1 = axes[0, 0]
            ax1.plot(time_arr * 1e6, voltage_arr, 'b-', label='Voltage', linewidth=0.8)
            ax1.set_xlabel('Time (µs)')
            ax1.set_ylabel('Voltage (V)', color='b')
            ax1.tick_params(axis='y', labelcolor='b')
            ax1b = ax1.twinx()
            ax1b.plot(time_arr * 1e6, current_arr * 1000, 'r-', label='Current', linewidth=0.8, alpha=0.7)
            ax1b.set_ylabel('Current (mA)', color='r')
            ax1b.tick_params(axis='y', labelcolor='r')
            ax1.set_title('Full Waveform')
            ax1.grid(True, alpha=0.3)
            
            # Zoom on a few steady-state cycles
            ax2 = axes[0, 1]
            if len(rising_edges) > skip_first + 3:
                zoom_start = rising_edges[skip_first]
                zoom_end = rising_edges[skip_first + 3]
                ax2.plot(time_arr[zoom_start:zoom_end] * 1e6, 
                        voltage_arr[zoom_start:zoom_end], 'b-', label='Voltage')
                ax2.set_xlabel('Time (µs)')
                ax2.set_ylabel('Voltage (V)', color='b')
                ax2b = ax2.twinx()
                ax2b.plot(time_arr[zoom_start:zoom_end] * 1e6, 
                         current_arr[zoom_start:zoom_end] * 1000, 'r-', label='Current')
                ax2b.set_ylabel('Current (mA)', color='r')
            ax2.set_title('Steady-State Detail (3 cycles)')
            ax2.grid(True, alpha=0.3)
            
            # Flux over time
            ax3 = axes[1, 0]
            ax3.plot(time_arr * 1e6, flux * 1e6, 'g-', linewidth=0.8)
            ax3.set_xlabel('Time (µs)')
            ax3.set_ylabel('Flux Linkage (µWb)')
            ax3.set_title(f'Flux Linkage (closure error: {result.flux_error_percent:.1f}%)')
            ax3.grid(True, alpha=0.3)
            
            # Energy per cycle
            ax4 = axes[1, 1]
            cycle_numbers = list(range(skip_first + 1, skip_first + 1 + len(energies)))
            ax4.bar(cycle_numbers, [e * 1e6 for e in energies], color='purple', alpha=0.7)
            ax4.axhline(result.energy_per_cycle_joules * 1e6, color='r', linestyle='--', 
                       label=f'Mean: {result.energy_per_cycle_joules*1e6:.3f} µJ')
            ax4.set_xlabel('Cycle Number')
            ax4.set_ylabel('Energy (µJ)')
            ax4.set_title(f'Energy per Cycle → P = {result.power_watts*1000:.2f} mW')
            ax4.legend()
            ax4.grid(True, alpha=0.3)
            
            plt.suptitle(f'Core Loss Measurement @ {frequency/1000:.1f} kHz, V = {voltage} V', 
                        fontsize=14, fontweight='bold')
            plt.tight_layout()
            
            if save_plot:
                filename = f'core_loss_{frequency/1000:.0f}kHz.png'
                plt.savefig(filename, dpi=150)
                print(f"\nPlot saved to {filename}")
            
            if plot:
                plt.show()
            else:
                plt.close()
        
        return result

    def run_core_loss_vs_frequency(self, voltage, frequencies, timing_ratios=None,
                                    num_pulses=50, plot=True, save_plot=True):
        """
        Measure core loss at multiple frequencies.
        
        Args:
            voltage: Supply voltage in V
            frequencies: List of frequencies in Hz
            timing_ratios: Dict mapping frequency to (t_pos, t_neg) tuples
                          If None, uses default ratio for half-bridge
            num_pulses: Number of pulses per measurement
            plot: Whether to display plot
            save_plot: Whether to save plot
            
        Returns:
            dict: Results for each frequency
        """
        import numpy as np
        import matplotlib.pyplot as plt
        
        # Default timing ratio based on half-bridge (V+ ≈ 9× |V-|)
        # This can be adjusted based on measured voltages
        default_t_pos_ratio = 0.09  # t+ is 9% of period
        
        results = []
        
        print("=" * 60)
        print("CORE LOSS vs FREQUENCY SWEEP")
        print("=" * 60)
        print(f"Voltage: {voltage} V")
        print(f"Frequencies: {[f/1000 for f in frequencies]} kHz")
        print("=" * 60)
        
        for freq in frequencies:
            T_period = 1.0 / freq
            
            if timing_ratios and freq in timing_ratios:
                t_pos, t_neg = timing_ratios[freq]
            else:
                # Default for half-bridge
                t_pos = T_period * default_t_pos_ratio
                t_neg = T_period - t_pos
            
            print(f"\n--- {freq/1000:.1f} kHz ---")
            result = self.measure_core_loss(
                voltage=voltage,
                t_positive=t_pos,
                t_negative=t_neg,
                num_pulses=num_pulses,
                plot=False,
                save_plot=False
            )
            
            if result.power_watts is not None:
                results.append({
                    'frequency': freq,
                    'power_mW': result.power_watts * 1000,
                    'flux_error': result.flux_error_percent,
                    'result': result
                })
        
        # Plot summary
        if results and (plot or save_plot):
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
            
            freqs = [r['frequency']/1000 for r in results]
            powers = [r['power_mW'] for r in results]
            errors = [r['flux_error'] for r in results]
            
            ax1.plot(freqs, powers, 'bo-', markersize=10, linewidth=2)
            ax1.set_xlabel('Frequency (kHz)')
            ax1.set_ylabel('Core Loss (mW)')
            ax1.set_title(f'Core Loss vs Frequency @ {voltage}V')
            ax1.grid(True, alpha=0.3)
            
            ax2.bar(freqs, errors, color='orange', alpha=0.7)
            ax2.axhline(5, color='g', linestyle='--', label='5% target')
            ax2.axhline(20, color='r', linestyle='--', label='20% limit')
            ax2.set_xlabel('Frequency (kHz)')
            ax2.set_ylabel('Flux Closure Error (%)')
            ax2.set_title('Measurement Quality')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            
            if save_plot:
                plt.savefig('core_loss_vs_frequency.png', dpi=150)
                print("\nPlot saved to core_loss_vs_frequency.png")
            
            if plot:
                plt.show()
            else:
                plt.close()
        
        return results


if __name__ == "__main__":

    with open(os.path.abspath(os.path.join(os.getcwd(), os.path.dirname(__file__), os.pardir, "hardware_configuration.json"))) as f:
        configuration = json.load(f)
        print(configuration)

    # === CORE LOSS MEASUREMENT (TPT Method) ===
    # RM10 N87 ungapped with 26 turns
    # Uses the IECON 2020 TPT paper method: E_core = ∫(V × I) dt
    
    tpt = InductanceMeasurement(**configuration)
    tpt.set_timeout_in_ms(5000)
    tpt.verbose = True
    
    # Define magnetic parameters
    params = tpt.CoreLossParameters(
        core_type='RM10',
        material='N87',
        number_turns=26,
        air_gap=0,                    # Ungapped
        frequency=50000,              # 50 kHz (achievable with half-bridge)
        flux_density_pp=0.003,        # ~3 mT (limited by half-bridge topology)
        v_positive_measured=6.76,     # Measured V+ from half-bridge
        v_negative_measured=-0.19     # Measured V- (body diode)
    )
    
    # Calculate timing and electrical parameters from magnetic info
    params = tpt.calculate_core_loss_parameters(params)
    
    # Run core loss measurement with optimal timing for this hardware
    # t+ = 0.5 µs (board minimum), t- = 19.5 µs (for volt-second balance)
    result = tpt.measure_core_loss(
        voltage=5.0,
        t_positive=0.5e-6,
        t_negative=19.5e-6,
        num_pulses=80,
        skip_first=20,
        skip_last=10,
        plot=True,
        save_plot=True
    )
    
    # Print final results
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Core: {params.core_type} {params.material}, N = {params.number_turns}")
    print(f"Calculated inductance: {params.inductance * 1000:.2f} mH")
    print(f"Frequency: {result.frequency_hz / 1000:.1f} kHz")
    print(f"Core loss: {result.power_watts * 1000:.3f} mW")
    print(f"Flux closure error: {result.flux_error_percent:.1f}%")
    print("=" * 60)

    # === INDUCTANCE MEASUREMENT (uncomment to run instead) ===
    # measure_parameters = InductanceMeasurement.MeasureParameters(
    #     core_type='RM10',
    #     material='N87',
    #     number_turns=26,
    #     air_gap=0,
    #     start_voltage=5.0,
    #     start_frequency=500000,
    #     min_frequency=5000,
    #     frequency_steps=20,
    #     saturation_threshold=0.30,
    #     max_flux_density=0.30,
    #     max_current=0.5,
    #     num_pulses=10
    # )
    # result = tpt.run_test(measure_parameters)
    # print(result.to_dataframe())


# =============================================================================
# DEVELOPMENT NOTES AND KNOWN ISSUES
# =============================================================================
#
# CURRENT PROBE SCALE (CRITICAL!)
# -------------------------------
# The current_probe_scale parameter is the most common source of measurement errors.
#
# For a probe rated at X mV/A (outputs X millivolts per Amp):
#   probe_scale = X / 1000
#
# Examples:
#   - 100 mV/A probe: probe_scale = 0.1
#   - 10 mV/A probe:  probe_scale = 0.01
#   - 1 V/A probe:    probe_scale = 1.0
#
# The conversion is: Current_Amps = Oscilloscope_Volts × probe_scale
#
# Common mistake: Using probe_scale = 10 for 100 mV/A probe (WRONG!)
# This gives currents 100× too high and inductance 100× too low.
#
#
# HARDWARE REQUIREMENTS
# ---------------------
# 1. Dual-channel power supply with independent voltage control
#    - CH1 provides +V for positive pulses
#    - CH2 provides -V for negative pulses
#    - Both must reach full voltage without current limiting
#
# 2. If CH2 shows current limiting with low voltage:
#    - Check for short circuit in H-bridge negative rail
#    - Verify MOSFET drivers are not damaged
#    - Check wiring connections on ST2402 board
#
#
# FLUX BALANCE (IMPORTANT FOR ACCURACY)
# -------------------------------------
# The standard calculate_test_parameters() adds padding for minimum capture time.
# This creates odd half-period count → residual magnetization.
#
# Solutions:
#   1. Use create_balanced_pulse_train() for zero-DC measurements
#   2. Call demagnetize() between measurements
#   3. Ensure pulse train has even half-period count
#
#
# MEASUREMENT ACCURACY
# --------------------
# Expected accuracy vs. Bode100 reference:
#   - Typical: ±20-30% at 100kHz
#   - Better at lower frequencies (10-50kHz)
#   - Worse at higher frequencies (>200kHz) due to parasitics
#
# Discrepancy sources:
#   1. Frequency-dependent permeability (μr drops with frequency)
#   2. Winding resistance and skin effect
#   3. Probe calibration
#   4. Core temperature
#   5. Ringing/switching transients affecting slope measurement
#
#
# TODO: FUTURE IMPROVEMENTS
# -------------------------
# [ ] Implement asymmetric voltage DC bias method as alternative to first long pulse
# [ ] Add automatic scope range optimization based on measured current
# [ ] Implement iterative L estimation for better DC bias accuracy
# [ ] Add temperature compensation for core material properties
# [ ] Implement B-H curve extraction from TPT measurements
# [ ] Add support for gapped cores with fringing factor calculation
# [ ] Implement multi-frequency characterization in single test run
# [ ] Add automated probe calibration routine
#
#
# REFERENCES
# ----------
# 1. TPT (Triple Pulse Test) method paper
# 2. Core manufacturer datasheets for N87, N97, N49 materials
# 3. PicoScope SDK documentation
# 4. BK Precision 9129B programming manual
#
# =============================================================================
