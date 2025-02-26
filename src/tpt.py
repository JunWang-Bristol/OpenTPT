from board import Board
from power_supply import PowerSupply
from oscilloscope import Oscilloscope
import matplotlib.pyplot as plt


class TPT():

    class TestParameters():
        def __init__(self, positive_voltage, negative_voltage):
            self.positive_voltage = positive_voltage
            self.negative_voltage = negative_voltage
            self.pulses_periods = []

    def __init__(self, power_supply, oscilloscope, board, power_supply_port="COM3", oscilloscope_port="COM5", board_port="COM6"):
        self.power_supply = self.setup_power_supply(power_supply, power_supply_port)
        self.oscilloscope = self.setup_oscilloscope(oscilloscope, oscilloscope_port)
        self.board = self.setup_board(board, board_port)

    def calculate_test_parameters(self, inductance, number_turns, magnetic_flux_density_peak, magnetic_flux_density_dc_bias, frequency):
        # do magic
        # hardcoded
        positive_voltage = 30
        negative_voltage = 30
        dc_bias_period = 100e-6
        steady_period = 10e-6
        steady_repetitions = 5
        demagnetization_period = 100e-6

        parameters = self.TestParameters(positive_voltage, negative_voltage)
        parameters.pulses_periods = [dc_bias_period]
        parameters.pulses_periods.extend([steady_period, steady_period] * steady_repetitions)
        parameters.pulses_periods.append(demagnetization_period)
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

    def run_test(self):
        positive_voltage = 30
        negative_voltage = 30
        dc_bias_period = 100e-6
        steady_period = 10e-6
        steady_repetitions = 5
        demagnetization_period = 100e-6

        parameters = self.TestParameters(positive_voltage, negative_voltage)
        parameters.pulses_periods = [dc_bias_period]
        parameters.pulses_periods.extend([steady_period, steady_period] * steady_repetitions)
        parameters.pulses_periods.append(demagnetization_period)

        # POWER SUPPLY SETUP START

        self.power_supply.disable_output(1)
        self.power_supply.disable_output(2)
        self.power_supply.reset_limits()

        self.power_supply.set_source_voltage(1, parameters.positive_voltage)
        read_voltage = float(self.power_supply.get_source_voltage(1))
        assert float(parameters.positive_voltage) == read_voltage, f"Wrong voltage measured at PSU: {read_voltage}, expected {parameters.positive_voltage}"

        self.power_supply.set_source_voltage(2, parameters.negative_voltage)
        read_voltage = float(self.power_supply.get_source_voltage(2))
        assert float(parameters.negative_voltage) == read_voltage, f"Wrong voltage measured at PSU: {read_voltage}, expected {parameters.negative_voltage}"

        # POWER SUPPLY SETUP END

        # OSCILLOSCOPE SETUP START

        self.oscilloscope.set_channel_configuration(
            channel=0, 
            input_voltage_range=20, 
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_channel_configuration(
            channel="B", 
            input_voltage_range=20, 
            coupling=0, 
            analog_offset=0
        )
        self.oscilloscope.set_rising_trigger(0, 3)
        self.oscilloscope.arm_trigger(0)

        # self.oscilloscope.set_number_samples(int(self.oscilloscope.get_maximum_samples()))
        self.oscilloscope.set_sampling_time(4e-09)

        # OSCILLOSCOPE SETUP STOP

        # BOARD SETUP START
        self.board.reset()
        self.board.clear_pulses()
        for pulse_period in parameters.pulses_periods:
            self.board.add_pulse(pulse_period)

        # BOARD SETUP STOP

        self.power_supply.enable_output(1)
        self.power_supply.enable_output(2)

        self.oscilloscope.run_acquisition_block()

        self.board.run_pulses(1)

        data = self.oscilloscope.read_data(
            channels=[0, 1]
        )

        for key, datum in data.items():
            plt.plot(datum["time"], datum["data"])
        plt.show()

        print(data)


if __name__ == "__main__":
    tpt = TPT(
        power_supply="BK9129B",
        power_supply_port="COM3",
        oscilloscope="PicoScope2408B",
        oscilloscope_port="COM5",
        board_port="COM6",
        board="NUCLEO-H503RB"
    )
    tpt.run_test()
