import unittest
import context  # noqa: F401
from oscilloscope import Oscilloscope
import random
import time


class BK9129B(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        #  out = Oscilloscope Under Test :)
        cls.out = Oscilloscope.factory("PicoScope2408B", "COM5")
        # cls.out.reset()
        print("Starting tests for PicoScope2408B")

    @classmethod
    def tearDownClass(cls):
        print("\nFinishing tests for PicoScope2408B")

    def test_get_status(self):
        self.assertEqual("PICO_MULTIPLE_DEVICES_FOUND", self.out.get_status(326))

    def test_get_number_channels(self):
        self.assertEqual(4, self.out.get_number_channels())

    def test_get_channel_index(self):
        self.assertEqual(3, self.out.get_channel_index('PS2000A_CHANNEL_D'))

    def test_get_input_voltage_ranges(self):
        self.assertEqual([0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0], self.out.get_input_voltage_ranges())

    def test_get_analog_offset_range(self):
        expectec_values = {
            0.02: [-0.25, 0.25],
            0.05: [-0.25, 0.25],
            0.1: [-0.25, 0.25],
            0.2: [-0.25, 0.25],
            0.5: [-2.5, 2.5],
            1.0: [-2.5, 2.5],
            2.0: [-2.5, 2.5],
            5.0: [-20.0, 20.0],
            10.0: [-20.0, 20.0],
            20.0: [-20.0, 20.0],
        }

        input_voltage_ranges = self.out.get_input_voltage_ranges()
        for input_voltage_range in input_voltage_ranges:
            analog_offset_range = self.out.get_analog_offset_range(0, input_voltage_range)
            self.assertEqual(expectec_values[input_voltage_range], analog_offset_range)

    def test_channel_configuration(self):
        for x in range(10):
            channel_index = random.randint(0, self.out.get_number_channels() - 1)
            coupling = random.randint(0, 1)
            input_voltage_range = random.choice(self.out.get_input_voltage_ranges())
            analog_offset_range = self.out.get_analog_offset_range(coupling, input_voltage_range)
            analog_offset = round(random.uniform(analog_offset_range[0], analog_offset_range[1]), 4)
            self.out.set_channel_configuration(channel_index, input_voltage_range, coupling, analog_offset)
            channel_configuration = self.out.get_channel_configuration(channel_index)
            self.assertEqual(input_voltage_range, channel_configuration.input_voltage_range)
            self.assertEqual(analog_offset, channel_configuration.analog_offset)
            self.assertEqual(coupling, channel_configuration.coupling)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
