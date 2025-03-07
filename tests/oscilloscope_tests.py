import unittest
import context  # noqa: F401
from oscilloscope import Oscilloscope
import random
import matplotlib.pyplot as plt
import os
import json


class OscilloscopesTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(os.path.abspath(os.path.join(os.getcwd(), os.path.dirname(__file__), os.pardir, "hardware_configuration.json"))) as f:
            cls.configuration = json.load(f)
            print(cls.configuration)

        #  out = Oscilloscope Under Test :)
        cls.out = Oscilloscope.factory(cls.configuration['oscilloscope'], cls.configuration['oscilloscope_port'])

        if cls.configuration['oscilloscope'] == "PicoScope2408B":
            cls.channel = 'PS2000A_CHANNEL_D'
            cls.input_voltage_ranges = [0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]
        elif cls.configuration['oscilloscope'] == "PicoScope3406D":
            cls.channel = 'PS3000A_CHANNEL_D'
            cls.input_voltage_ranges = [0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]
        elif cls.configuration['oscilloscope'] == "PicoScope6404D":
            cls.channel = 'PS6000_CHANNEL_D'
            cls.input_voltage_ranges = [0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]
        else:
            assert 0, "Unknown oscilloscope"

        print(f"Starting tests for {cls.configuration['oscilloscope']}")

    @classmethod
    def tearDownClass(cls):
        print(f"\nFinishing tests for {cls.configuration['oscilloscope']}")

    def test_get_status(self):
        self.assertEqual("PICO_MULTIPLE_DEVICES_FOUND", self.out.get_status(326))

    def test_get_number_channels(self):
        self.assertEqual(4, self.out.get_number_channels())

    def test_get_channel_index(self):
        self.assertEqual(3, self.out.get_channel_index(self.channel))

    def test_get_input_voltage_ranges(self):
        self.assertEqual(self.input_voltage_ranges, self.out.get_input_voltage_ranges())

    def test_check_channel(self):
        self.assertEqual(0, self.out.check_channel(0.0))
        self.assertEqual(0, self.out.check_channel("0"))
        self.assertEqual(0, self.out.check_channel("A"))

        self.assertEqual(1, self.out.check_channel(1.0))
        self.assertEqual(1, self.out.check_channel("1"))
        self.assertEqual(1, self.out.check_channel("B"))

        self.assertEqual(2, self.out.check_channel(2.0))
        self.assertEqual(2, self.out.check_channel("2"))
        self.assertEqual(2, self.out.check_channel("C"))

        self.assertEqual(3, self.out.check_channel(3.0))
        self.assertEqual(3, self.out.check_channel("3"))
        self.assertEqual(3, self.out.check_channel("D"))

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

    def test_maximum_ADC_count(self):
        value = self.out.get_maximum_ADC_count()
        self.assertEqual(32512, value)

    def test_minimum_ADC_count(self):
        value = self.out.get_minimum_ADC_count()
        self.assertEqual(-32512, value)

    def test_trigger(self):
        for x in range(10):
            channel = random.randint(0, self.out.get_number_channels() - 1)
            input_voltage_range = random.choice(self.out.get_input_voltage_ranges())
            threshold_voltage = round(random.uniform(0, input_voltage_range), 4)
            delayed_samples = random.randint(0, 500)
            timeout = random.randint(0, 10000)

            self.assertFalse(self.out.is_trigger_armed())
            self.out.set_channel_configuration(channel, input_voltage_range, 0, 0.2)
            direction = bool(random.randint(0, 1))
            if direction:
                self.out.set_rising_trigger(channel, threshold_voltage, delayed_samples, timeout)
            else:
                self.out.set_falling_trigger(channel, threshold_voltage, delayed_samples, timeout)

            self.assertTrue(self.out.is_trigger_armed())
            self.out.disarm_trigger(channel)
            self.assertFalse(self.out.is_trigger_armed())
            self.out.arm_trigger(channel)
            self.assertTrue(self.out.is_trigger_armed())
            self.out.disarm_trigger(channel)

            configuration = self.out.get_trigger_configuration(channel)
            self.assertEqual(threshold_voltage, configuration.threshold_voltage)
            self.assertEqual(2 if direction else 3, configuration.direction)
            self.assertEqual(delayed_samples, configuration.delayed_samples)
            self.assertEqual(timeout, configuration.timeout)

    def test_real_sampling_time(self):
        for x in range(10):
            timebase = random.randint(0, 2**32 - 1)
            desired_time = self.out.convert_timebase_to_time(timebase)
            real_sampling_time = self.out.get_real_sampling_time(desired_time, 12345)
            self.assertAlmostEqual(desired_time, real_sampling_time, None, "", desired_time * 0.1)

    def test_read_data(self):
        self.out.set_channel_configuration(
            channel=0, 
            input_voltage_range=5, 
            coupling=0, 
            analog_offset=0
        )
        self.out.set_channel_configuration(
            channel="B", 
            input_voltage_range=9, 
            coupling=0, 
            analog_offset=0
        )
        self.out.set_rising_trigger(0, 3)
        self.out.disarm_trigger(0)

        number_samples = int(self.out.get_maximum_samples())
        desired_time = 1e-09
        sampling_time = self.out.set_sampling_time(desired_time)

        self.assertEqual(4e-9, sampling_time)
        self.out.run_acquisition_block(sampling_time, number_samples)

        data = self.out.read_data(
            channels=[0, "B"],
            number_samples=number_samples
        )

        self.assertEqual(number_samples, len(data["time"]))
        self.assertEqual(number_samples, len(data[0]))
        self.assertEqual(number_samples, len(data["B"]))

        self.out.run_acquisition_block(sampling_time, number_samples)

        self.out.set_channel_skew(0, 2e-9)
        self.out.set_channel_skew("B", -9e-9)

        data = self.out.read_data(
            channels=[0, "B"],
            number_samples=number_samples
        )

        self.assertEqual(number_samples * 4, len(data["time"]))
        self.assertEqual(number_samples * 4, len(data[0]))
        self.assertEqual(number_samples * 4, len(data["B"]))

        # plt.plot(data["time"], data[0])
        # plt.plot(data["time"], data["B"])
        # plt.show()

    @unittest.skip
    def test_read_data_trigger(self):
        self.out.set_channel_configuration(
            channel=0, 
            input_voltage_range=5, 
            coupling=0, 
            analog_offset=0
        )
        self.out.set_channel_configuration(
            channel="B", 
            input_voltage_range=9, 
            coupling=0, 
            analog_offset=0
        )
        self.out.set_rising_trigger(0, 3)
        self.out.arm_trigger(0)

        number_samples = int(self.out.get_maximum_samples() * 0.1)
        desired_time = 4e-09
        self.out.run_acquisition_block(desired_time, number_samples)

        data = self.out.read_data(
            channels=[0, "B"],
            number_samples=number_samples
        )

        print(data)
        self.assertEqual(number_samples, len(data["time"]))
        self.assertEqual(number_samples, len(data[0]))
        self.assertEqual(number_samples, len(data["B"]))

        # plt.plot(data["time"], data[0])
        # plt.plot(data["time"], data["B"])
        # plt.show()


if __name__ == '__main__':  # pragma: no cover
    unittest.main()


# 6404D
# 3406D