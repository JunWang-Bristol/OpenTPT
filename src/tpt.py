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
        def __init__(self, positive_voltage, negative_voltage, current_peak, pulses_periods):
            self.positive_voltage = positive_voltage
            self.negative_voltage = negative_voltage
            self.current_peak = negative_voltage
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
        positive_voltage = measure_parameters.effective_area * measure_parameters.number_turns * measure_parameters.magnetic_flux_density_ac_peak_to_peak / 2 / steady_period
        negative_voltage = positive_voltage
        dc_bias_period = measure_parameters.effective_area * measure_parameters.number_turns * measure_parameters.magnetic_flux_density_dc_bias / positive_voltage
        steady_repetitions = 5  # hardcoded
        demagnetization_period = dc_bias_period
        current_peak_to_peak = measure_parameters.magnetic_flux_density_ac_peak_to_peak * measure_parameters.number_turns / (measure_parameters.inductance * measure_parameters.effective_area)
        current_dc_bias = measure_parameters.magnetic_flux_density_dc_bias * measure_parameters.number_turns / (measure_parameters.inductance * measure_parameters.effective_area)
        current_peak = current_dc_bias * current_peak_to_peak / 2

        pulses_periods = [dc_bias_period]
        pulses_periods.extend([steady_period, steady_period] * steady_repetitions)
        pulses_periods.append(demagnetization_period)
        parameters = self.TestParameters(positive_voltage, negative_voltage, current_peak, pulses_periods)
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

        self.power_supply.set_source_voltage(
            channel=1,
            voltage=parameters.positive_voltage
        )
        read_voltage = float(round(self.power_supply.get_source_voltage(channel=1), 6))
        assert float(round(parameters.positive_voltage, 6)) == read_voltage, f"Wrong voltage measured at PSU: {read_voltage}, expected {parameters.positive_voltage}"

        self.power_supply.set_source_voltage(
            channel=2,
            voltage=parameters.negative_voltage
        )
        read_voltage = float(round(self.power_supply.get_source_voltage(channel=2), 6))
        assert float(round(parameters.negative_voltage, 6)) == read_voltage, f"Wrong voltage measured at PSU: {read_voltage}, expected {parameters.negative_voltage}"

        if startup:
            result = self.power_supply.enable_series_mode()
            assert result, "Power supply did not enter series mode"

    def setup_oscilloscope(self, parameters):
        self.oscilloscope.set_channel_configuration(
            channel=0, 
            input_voltage_range=parameters.positive_voltage,  # TODO: inckude probe scaling
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_channel_configuration(
            channel=1, 
            input_voltage_range=parameters.positive_voltage,  # TODO: inckude probe scaling
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_channel_configuration(
            channel=2, 
            input_voltage_range=parameters.current_peak,  # TODO: inckude probe scaling
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_rising_trigger(
            channel=0,
            threshold_voltage=0.1 * parameters.positive_voltage,  # Hardcoded TODO: inckude probe scaling
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
        self.oscilloscope.set_channel_skew(1, -9e-9)  # TODO: Totally made up skew
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

    def calculate_core_losses(self, parameters, data):
        number_upsampled_pre_trigger_samples = self.oscilloscope.get_number_upsampled_pre_trigger_samples()
        upsampled_sampling_time = self.oscilloscope.get_upsampled_sampling_time()

        dc_bias_number_samples = int(parameters.pulses_periods[0] / upsampled_sampling_time)
        # dc_bias_data = data.iloc[number_upsampled_pre_trigger_samples: number_upsampled_pre_trigger_samples + dc_bias_number_samples]
        # plt.plot(dc_bias_data["time"], dc_bias_data["Output Voltage"])
        pulses_data = []
        previous_pulses_number_samples = number_upsampled_pre_trigger_samples + dc_bias_number_samples
        for pulse_pair_index in range(1, len(parameters.pulses_periods) - 1, 2):
            pulse_pair_number_samples = int((parameters.pulses_periods[pulse_pair_index] + parameters.pulses_periods[pulse_pair_index + 1]) / upsampled_sampling_time)
            pulses_datum = data.iloc[previous_pulses_number_samples: previous_pulses_number_samples + pulse_pair_number_samples]
            previous_pulses_number_samples += pulse_pair_number_samples
            pulses_data.append(pulses_datum)
            # plt.plot(pulses_datum["time"], pulses_datum["Output Voltage"])
            # print(pulse_pair_index)
            # plt.show()

        energy = pulses_data[-1]["Output Voltage"] * pulses_data[-1]["Current"]
        core_losses = energy.sum() * upsampled_sampling_time
        # print(energy)
        # print(core_losses)
        # demagnetization_data = data.iloc[previous_pulses_number_samples: int(parameters.pulses_periods[-1] / upsampled_sampling_time)]
        # assert 0
        # plt.plot(demagnetization_data["time"], demagnetization_data["Output Voltage"])
        # plt.show()
        return core_losses

    def run_test(self, measure_parameters):
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
        while data is None:

            self.oscilloscope.run_acquisition_block()

            self.board.run_pulses(
                number_repetitions=1
            )

            data = self.oscilloscope.read_data()
            break
            if not math.isclose(data["Output Voltage"].max(), parameters.positive_voltage, rel_tol=self.maximum_voltage_error):
                difference = data["Output Voltage"].max() - parameters.positive_voltage
                aux_parameters = copy.deepcopy(parameters)
                aux_parameters.positive_voltage += difference
                self.setup_power_supply(aux_parameters)
                data = None

        core_losses = self.calculate_core_losses(parameters, data)
        # for key, datum in data["data"].items():
        #     plt.plot(data["time"], datum)
        # plt.show()

        # print(data)
        print(f"core_losses: {core_losses} W")


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
        frequency=100000,
        inductance=1e3,
    )
    tpt.run_test(measure_parameters)
