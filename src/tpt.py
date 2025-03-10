from board import Board
from power_supply import PowerSupply
from oscilloscope import Oscilloscope
import matplotlib.pyplot as plt
import os
import json
import math
import copy


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
        def __init__(self, voltage_peak_to_peak, current_peak, pulses_periods):
            self.voltage_peak_to_peak = voltage_peak_to_peak
            self.current_peak = current_peak
            self.pulses_periods = pulses_periods
            self.total_time = sum(pulses_periods)

    def __init__(self, power_supply, oscilloscope, board, power_supply_port, oscilloscope_port, board_port):
        self.power_supply = self.instantiate_power_supply(power_supply, power_supply_port)
        self.oscilloscope = self.instantiate_oscilloscope(oscilloscope, oscilloscope_port)
        self.board = self.instantiate_board(board, board_port)
        self.timeout = 5000
        self.maximum_voltage_error = 0.05

    def set_timeout_in_ms(self, timeout):
        self.timeout = timeout

    def set_maximum_voltage_error(self, maximum_voltage_error):
        self.maximum_voltage_error = maximum_voltage_error

    def calculate_test_parameters(self, measure_parameters):
        steady_period = 1.0 / (2 * measure_parameters.frequency)
        voltage_peak_to_peak = measure_parameters.effective_area * measure_parameters.number_turns * measure_parameters.magnetic_flux_density_ac_peak_to_peak / steady_period
        dc_bias_period = measure_parameters.effective_area * measure_parameters.number_turns * measure_parameters.magnetic_flux_density_dc_bias / (voltage_peak_to_peak / 2)
        steady_repetitions = 5  # hardcoded
        demagnetization_period = dc_bias_period
        current_peak_to_peak = measure_parameters.magnetic_flux_density_ac_peak_to_peak * measure_parameters.number_turns / (measure_parameters.inductance * measure_parameters.effective_area)
        current_dc_bias = measure_parameters.magnetic_flux_density_dc_bias * measure_parameters.number_turns / (measure_parameters.inductance * measure_parameters.effective_area)
        current_peak = current_dc_bias * current_peak_to_peak / 2

        print(f"measure_parameters.effective_area: {measure_parameters.effective_area}")
        print(f"dc_bias_period: {dc_bias_period}")
        print(f"steady_period: {steady_period}")
        print(f"voltage_peak_to_peak: {voltage_peak_to_peak}")
        pulses_periods = [dc_bias_period]
        pulses_periods.extend([steady_period, steady_period] * steady_repetitions)
        pulses_periods.append(demagnetization_period)
        parameters = self.TestParameters(voltage_peak_to_peak, current_peak, pulses_periods)
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

            result = self.power_supply.enable_series_mode()
            assert result, "Power supply did not enter series mode"

        self.power_supply.set_source_voltage(
            channel=1,
            voltage=parameters.voltage_peak_to_peak
        )
        read_voltage = float(round(self.power_supply.get_source_voltage(channel=1), 6))
        assert float(round(parameters.voltage_peak_to_peak, 6)) == read_voltage, f"Wrong voltage measured at PSU: {read_voltage}, expected {parameters.voltage_peak_to_peak}"

        # self.power_supply.set_source_voltage(
        #     channel=2,
        #     voltage=parameters.voltage_peak_to_peak
        # )
        # read_voltage = float(round(self.power_supply.get_source_voltage(channel=2), 6))
        # assert float(round(parameters.voltage_peak_to_peak, 6)) == read_voltage, f"Wrong voltage measured at PSU: {read_voltage}, expected {parameters.negative_voltage}"

    def setup_oscilloscope(self, parameters):
        self.oscilloscope.set_channel_configuration(
            channel=0, 
            input_voltage_range=parameters.voltage_peak_to_peak,  # TODO: include probe scaling
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_channel_configuration(
            channel=1, 
            input_voltage_range=parameters.voltage_peak_to_peak,  # TODO: include probe scaling
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_channel_configuration(
            channel=2, 
            input_voltage_range=parameters.current_peak,  # TODO: include probe scaling
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_rising_trigger(
            channel=0,
            threshold_voltage=0.1 * parameters.voltage_peak_to_peak,  # Hardcoded TODO: include probe scaling
            timeout=self.timeout
        )
        self.oscilloscope.arm_trigger(
            channel=0
        )

        self.oscilloscope.set_number_samples(int(self.oscilloscope.get_maximum_samples()))
        desired_sampling_time = parameters.total_time / self.oscilloscope.get_maximum_samples()
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

        self.oscilloscope.set_channel_skew(0, 2e-9)  # TODO: Totally made up skew
        self.oscilloscope.set_channel_skew(1, 0)
        self.oscilloscope.set_channel_skew(2, 5e-9)  # TODO: Totally made up skew

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
        return pulses_data[-1].abs().mean()["Output Voltage"]

    def calculate_core_losses(self, parameters, data):
        upsampled_sampling_time = self.oscilloscope.get_upsampled_sampling_time()
        pulses_data = self.get_pulses(parameters, data)

        energy = pulses_data[-1]["Output Voltage"] * pulses_data[-1]["Current"]
        core_losses = energy.sum() * upsampled_sampling_time
        return core_losses

    def run_test(self, measure_parameters):
        plot = False
        adjust_voltage = False
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
        aux_parameters = copy.deepcopy(parameters)
        while data is None:

            self.oscilloscope.run_acquisition_block()

            self.board.run_pulses(
                number_repetitions=1
            )

            data = self.oscilloscope.read_data()

            if plot:
                plt.plot(data["time"], data["Input Voltage"])
                plt.plot(data["time"], data["Output Voltage"])
                plt.show()

            average_peak_pulses = self.get_average_peak_output_voltage_pulses(parameters, data)
            print(average_peak_pulses)
            print(average_peak_pulses)

            if not math.isclose(average_peak_pulses, parameters.voltage_peak_to_peak / 2, rel_tol=self.maximum_voltage_error) and adjust_voltage:
                difference = parameters.voltage_peak_to_peak / 2 - average_peak_pulses
                aux_parameters.voltage_peak_to_peak += difference
                self.setup_power_supply(aux_parameters)
                print(f'average_peak_pulses: {average_peak_pulses}')
                print(f'original parameters.voltage_peak_to_peak / 2: {parameters.voltage_peak_to_peak / 2}')
                print(f'aux_parameters.voltage_peak_to_peak / 2: {aux_parameters.voltage_peak_to_peak / 2}')
                print(f'difference: {difference}')
                data = None

        core_losses = self.calculate_core_losses(parameters, data)

        print(f"core_losses: {core_losses} W")

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
        effective_area=0.0000350,
        number_turns=5,
        magnetic_flux_density_ac_peak_to_peak=0.2,
        magnetic_flux_density_dc_bias=0.2,
        frequency=50000,
        inductance=1e3,
    )
    tpt.run_test(measure_parameters)
