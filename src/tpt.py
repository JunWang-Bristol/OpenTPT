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


class TPT():

    class MeasureParameters():
        def __init__(self, effective_area, number_turns, magnetic_flux_density_ac_peak_to_peak, magnetic_flux_density_dc_bias, frequency, inductance):
            self.effective_area = effective_area
            self.number_turns = number_turns
            self.magnetic_flux_density_ac_peak_to_peak = magnetic_flux_density_ac_peak_to_peak
            self.magnetic_flux_density_dc_bias = magnetic_flux_density_dc_bias
            self.frequency = frequency
            self.inductance = inductance

    class TestParameters():
        def __init__(self, positive_voltage_peak, negative_voltage_peak, current_peak, pulses_periods):
            self.positive_voltage_peak = positive_voltage_peak
            self.negative_voltage_peak = negative_voltage_peak
            self.current_peak = current_peak
            self.pulses_periods = pulses_periods
            self.total_time = sum(pulses_periods)

    def __init__(self, power_supply, oscilloscope, board, power_supply_port, oscilloscope_port, board_port, input_voltage_probe_scale=1, output_voltage_probe_scale=1, current_probe_scale=1):
        self.power_supply = self.instantiate_power_supply(power_supply, power_supply_port)
        self.oscilloscope = self.instantiate_oscilloscope(oscilloscope, oscilloscope_port)
        self.input_voltage_probe_scale = input_voltage_probe_scale
        self.output_voltage_probe_scale = output_voltage_probe_scale
        self.current_probe_scale = current_probe_scale
        self.board = self.instantiate_board(board, board_port)
        self.timeout = 5000
        self.maximum_voltage_error = 0.05
        self.voltage_positive_proportion = 0.5
        self.measured_inductance = None
        self.desired_current_dc_bias = 0
        self.post_processor = post_processor.PostProcessor()

    def set_timeout_in_ms(self, timeout):
        self.timeout = timeout

    def set_maximum_voltage_error(self, maximum_voltage_error):
        self.maximum_voltage_error = maximum_voltage_error

    def calculate_test_parameters(self, measure_parameters):
        steady_period = 1.0 / (2 * measure_parameters.frequency)
        voltage_peak_to_peak = measure_parameters.effective_area * measure_parameters.number_turns * measure_parameters.magnetic_flux_density_ac_peak_to_peak / steady_period
        steady_repetitions = 7  # hardcoded

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

        pulses_periods = []
        pulses_periods.extend([steady_period, steady_period] * steady_repetitions)

        parameters = self.TestParameters(voltage_peak_to_peak * self.voltage_positive_proportion, voltage_peak_to_peak * (1 - self.voltage_positive_proportion), current_peak, pulses_periods)
        #parameters = self.TestParameters(voltage_peak_to_peak / 2 , voltage_peak_to_peak / 2, current_peak, pulses_periods)
        return parameters

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

            # result = self.power_supply.enable_series_mode()
            # assert result, "Power supply did not enter series mode"

        self.power_supply.set_source_voltage(
            channel=1,
            voltage=parameters.positive_voltage_peak
        )
        read_voltage = float(round(self.power_supply.get_source_voltage(channel=1), 6))
        assert float(round(parameters.positive_voltage_peak, 6)) == read_voltage, f"Wrong voltage measured at PSU: {read_voltage}, expected {parameters.positive_voltage_peak}"

        self.power_supply.set_source_voltage(
            channel=2,
            voltage=parameters.negative_voltage_peak
        )
        read_voltage = float(round(self.power_supply.get_source_voltage(channel=2), 6))
        assert float(round(parameters.negative_voltage_peak, 6)) == read_voltage, f"Wrong voltage measured at PSU: {read_voltage}, expected {parameters.negative_voltage_peak}"

    def setup_oscilloscope(self, parameters):
        self.oscilloscope.set_channel_configuration(
            channel=0, 
            input_voltage_range=parameters.positive_voltage_peak / self.input_voltage_probe_scale,
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_channel_configuration(
            channel=1, 
            input_voltage_range=parameters.negative_voltage_peak / self.output_voltage_probe_scale,
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_channel_configuration(
            channel=2, 
            input_voltage_range=parameters.current_peak / self.current_probe_scale,
            # input_voltage_range=1, 
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_rising_trigger(
            channel=0,
            threshold_voltage=parameters.positive_voltage_peak / self.output_voltage_probe_scale * 0.1,
            timeout=self.timeout
        )
        self.oscilloscope.arm_trigger(
            channel=0
        )

        self.oscilloscope.set_number_samples(int(self.oscilloscope.get_maximum_samples()))
        # self.oscilloscope.set_number_samples(10000)
        desired_sampling_time = parameters.total_time / self.oscilloscope.get_maximum_samples()
        # desired_sampling_time = parameters.total_time / 10000
        print(desired_sampling_time)
        actual_sampling_time = self.oscilloscope.set_sampling_time(desired_sampling_time)
        print(actual_sampling_time)
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

    def enumerate2(xs, start=0, step=1):
        for x in xs:
            yield (start, x)
            start += step

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

        # Test start

        self.power_supply.enable_output(
            channel=1
        )
        self.power_supply.enable_output(
            channel=2
        )

        data = None
        adjusted_parameters = copy.deepcopy(parameters)
        while data is None:

            print("Running block acquisition")
            self.oscilloscope.run_acquisition_block()

            time.sleep(1)
            print("Running pulses")
            self.board.run_pulses(
                number_repetitions=1
            )

            print("Reading data")
            data = self.oscilloscope.read_data()
            data.to_csv("test_data_gas.csv")
            print("Trigger!!")

            if plot:
                plt.plot(data["time"], data["Input Voltage"])
                plt.plot(data["time"], data["Output Voltage"])
                plt.plot(data["time"], data["Current"])
                plt.show()

            error, best_loop = self.post_processor.analyze_loops(data)
            if adjust_voltage_proportion and error > 0.05:
                print("Adjunsting voltage")
                # self.voltage_positive_proportion = self.post_processor.calculate_new_voltage_proportion(best_loop, self.desired_current_dc_bias, self.voltage_positive_proportion)
                self.voltage_positive_proportion = self.post_processor.calculate_new_voltage_proportion(best_loop, self.desired_current_dc_bias)
                adjusted_parameters = self.calculate_test_parameters(measure_parameters)
                self.setup_power_supply(adjusted_parameters)
                self.setup_oscilloscope(adjusted_parameters)
                self.setup_board(adjusted_parameters)

            else:
                data = None

        core_losses = self.calculate_core_losses(adjusted_parameters, data)

        print(f"core_losses: {core_losses} W")

        self.power_supply.disable_output(
            channel=1
        )
        self.power_supply.disable_output(
            channel=2
        )

        return core_losses, data


if __name__ == "__main__":

    with open(os.path.abspath(os.path.join(os.getcwd(), os.path.dirname(__file__), os.pardir, "hardware_configuration.json"))) as f:
        configuration = json.load(f)
        print(configuration)

    tpt = TPT(
        **configuration
    )
    tpt.set_timeout_in_ms(5000)
    tpt.set_maximum_voltage_error(0.1)

    measure_parameters = TPT.MeasureParameters(
        effective_area=0.0000650,
        number_turns=10,
        magnetic_flux_density_ac_peak_to_peak=0.05,
        magnetic_flux_density_dc_bias=0.15,
        frequency=50000,
        inductance=9e-6,
        # effective_area=0.0000350,
        # number_turns=5,
        # magnetic_flux_density_ac_peak_to_peak=0.2,
        # magnetic_flux_density_dc_bias=0.2,
        # frequency=50000,
        # inductance=1e3,
    )
    tpt.run_test(measure_parameters)

