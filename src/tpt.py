from board import Board
from power_supply import PowerSupply
from oscilloscope import Oscilloscope
import matplotlib.pyplot as plt
import os
import json


class TPT():

    class MeasureParameters():
        def __init__(self, effective_area, number_turns, magnetic_flux_density_ac_peak_to_peak, magnetic_flux_density_dc_bias, frequency):
            self.effective_area = effective_area
            self.number_turns = number_turns
            self.magnetic_flux_density_ac_peak_to_peak = magnetic_flux_density_ac_peak_to_peak
            self.magnetic_flux_density_dc_bias = magnetic_flux_density_dc_bias
            self.frequency = frequency

    class TestParameters():
        def __init__(self, positive_voltage, negative_voltage):
            self.positive_voltage = positive_voltage
            self.negative_voltage = negative_voltage
            self.pulses_periods = []
            self.total_time = None

    def __init__(self, power_supply, oscilloscope, board, power_supply_port, oscilloscope_port, board_port):
        self.power_supply = self.setup_power_supply(power_supply, power_supply_port)
        self.oscilloscope = self.setup_oscilloscope(oscilloscope, oscilloscope_port)
        self.board = self.setup_board(board, board_port)

    def calculate_test_parameters(self, measure_parameters):
        steady_period = 1.0 / (2 * measure_parameters.frequency)
        positive_voltage = measure_parameters.effective_area * measure_parameters.number_turns * measure_parameters.magnetic_flux_density_ac_peak_to_peak / 2 / steady_period
        negative_voltage = positive_voltage
        dc_bias_period = measure_parameters.effective_area * measure_parameters.number_turns * measure_parameters.magnetic_flux_density_dc_bias / positive_voltage
        steady_repetitions = 5  # hardcoded
        demagnetization_period = dc_bias_period

        parameters = self.TestParameters(positive_voltage, negative_voltage)
        parameters.pulses_periods = [dc_bias_period]
        parameters.pulses_periods.extend([steady_period, steady_period] * steady_repetitions)
        parameters.pulses_periods.append(demagnetization_period)
        parameters.total_time = sum(parameters.pulses_periods)
        return parameters

    def setup_power_supply(self, power_supply, port):
        power_supply = PowerSupply.factory(power_supply, port)
        return power_supply

    def setup_oscilloscope(self, oscilloscope, port):
        oscilloscope = Oscilloscope.factory(oscilloscope, port)
        return oscilloscope

    def setup_board(self, board, port):
        board = Board.factory(board, port)
        return board

    def run_test(self, measure_parameters):
        parameters = self.calculate_test_parameters(measure_parameters)

        # POWER SUPPLY SETUP START

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

        self.power_supply.set_source_voltage(2, parameters.negative_voltage)
        read_voltage = float(round(self.power_supply.get_source_voltage(channel=2), 6))
        assert float(round(parameters.negative_voltage, 6)) == read_voltage, f"Wrong voltage measured at PSU: {read_voltage}, expected {parameters.negative_voltage}"

        result = self.power_supply.enable_series_mode()
        assert result, "Power supply did not enter series mode"

        # POWER SUPPLY SETUP END

        # OSCILLOSCOPE SETUP START

        self.oscilloscope.set_channel_configuration(
            channel=0, 
            input_voltage_range=parameters.positive_voltage, 
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_channel_configuration(
            channel="B", 
            input_voltage_range=parameters.positive_voltage, 
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_rising_trigger(
            channel=0,
            threshold_voltage=3,
            timeout=5000
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

        self.oscilloscope.set_channel_skew(0, 2e-9)  # Totally made up skew
        self.oscilloscope.set_channel_skew(1, -9e-9)  # Totally made up skew

        # OSCILLOSCOPE SETUP STOP

        # BOARD SETUP START
        self.board.reset()
        self.board.clear_pulses()
        for pulse_period in parameters.pulses_periods:
            self.board.add_pulse(
                pulse_period=pulse_period
            )

        # BOARD SETUP STOP

        self.power_supply.enable_output(
            channel=1
        )
        self.power_supply.enable_output(
            channel=2
        )

        self.oscilloscope.run_acquisition_block()

        self.board.run_pulses(
            number_repetitions=1
        )

        data = self.oscilloscope.read_data(
            channels=[0, 1]
        )

        for key, datum in data["data"].items():
            plt.plot(data["time"], datum)
        plt.show()

        print(data)


if __name__ == "__main__":

    with open(os.path.abspath(os.path.join(os.getcwd(), os.path.dirname(__file__), os.pardir, "hardware_configuration.json"))) as f:
        configuration = json.load(f)
        print(configuration)

    tpt = TPT(
        **configuration
    )

    measure_parameters = TPT.MeasureParameters(
        effective_area=0.0000638,
        number_turns=5,
        magnetic_flux_density_ac_peak_to_peak=0.2,
        magnetic_flux_density_dc_bias=0.2,
        frequency=100000,
    )
    tpt.run_test(measure_parameters)
