import unittest
import context  # noqa: F401
from power_supply import PowerSupply
import random
import time


class BK9129B(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.psut = PowerSupply.factory("BK9129B", "COM3")
        cls.psut.reset()
        print("Starting tests for BK9129B")

    @classmethod
    def tearDownClass(cls):
        print("\nFinishing tests for BK9129B")

    def test_version(self):
        self.assertEqual("1991.1", self.psut.get_version())

    def test_maximum_voltage(self):
        print("test_maximum_voltage")
        maximum_source_voltage = self.psut.get_maximum_source_voltage(1)
        self.assertEqual(31, maximum_source_voltage)
        maximum_source_voltage = self.psut.get_maximum_source_voltage(2)
        self.assertEqual(31, maximum_source_voltage)
        maximum_source_voltage = self.psut.get_maximum_source_voltage(3)
        self.assertEqual(6, maximum_source_voltage)

    def test_minimum_voltage(self):
        print("test_minimum_voltage")
        minimum_source_voltage = self.psut.get_minimum_source_voltage(1)
        self.assertEqual(0, minimum_source_voltage)
        minimum_source_voltage = self.psut.get_minimum_source_voltage(2)
        self.assertEqual(0, minimum_source_voltage)
        minimum_source_voltage = self.psut.get_minimum_source_voltage(3)
        self.assertEqual(0, minimum_source_voltage)

    def test_maximum_current(self):
        print("test_maximum_current")
        maximum_source_current = self.psut.get_maximum_source_current(1)
        self.assertEqual(3.1, maximum_source_current)
        maximum_source_current = self.psut.get_maximum_source_current(2)
        self.assertEqual(3.1, maximum_source_current)
        maximum_source_current = self.psut.get_maximum_source_current(3)
        self.assertEqual(3.1, maximum_source_current)

    def test_minimum_current(self):
        print("test_minimum_current")
        minimum_source_current = self.psut.get_minimum_source_current(1)
        self.assertEqual(0, minimum_source_current)
        minimum_source_current = self.psut.get_minimum_source_current(2)
        self.assertEqual(0, minimum_source_current)
        minimum_source_current = self.psut.get_minimum_source_current(3)
        self.assertEqual(0, minimum_source_current)

    def test_source_voltage(self):
        print("test_source_voltage")
        available_channels = self.psut.get_available_channels()
        for x in range(10):
            channel = random.choice(available_channels)
            maximum_source_voltage = self.psut.get_maximum_source_voltage(channel)
            minimum_source_voltage = self.psut.get_minimum_source_voltage(channel)
            voltage = round(random.uniform(minimum_source_voltage, maximum_source_voltage), 4)
            self.psut.set_source_voltage(channel, voltage)
            read_voltage = self.psut.get_source_voltage(channel)
            self.assertEqual(voltage, read_voltage)

    def test_all_source_voltages(self):
        print("test_all_source_voltages")
        available_channels = self.psut.get_available_channels()
        for x in range(10):
            voltages = []
            for channel in available_channels:
                maximum_source_voltage = self.psut.get_maximum_source_voltage(channel)
                minimum_source_voltage = self.psut.get_minimum_source_voltage(channel)
                voltage = round(random.uniform(minimum_source_voltage, maximum_source_voltage), 4)
                voltages.append(voltage)
            self.psut.set_all_source_voltages(voltages)
            read_voltage = self.psut.get_all_source_voltages()
            self.assertEqual(voltages, read_voltage)

    def test_voltage_limit(self):
        print("test_voltage_limit")
        available_channels = self.psut.get_available_channels()
        for x in range(10):
            channel = random.choice(available_channels)
            maximum_voltage_limit = self.psut.get_maximum_source_voltage(channel)
            minimum_voltage_limit = self.psut.get_minimum_source_voltage(channel)
            limit = round(random.uniform(minimum_voltage_limit, maximum_voltage_limit), 4)
            self.psut.set_voltage_limit(channel, limit)
            read_limit = self.psut.get_voltage_limit(channel)
            self.assertEqual(limit, read_limit)

    def test_current_limit(self):
        print("test_current_limit")
        available_channels = self.psut.get_available_channels()
        for x in range(10):
            channel = random.choice(available_channels)
            maximum_current_limit = self.psut.get_maximum_source_current(channel)
            minimum_current_limit = self.psut.get_minimum_source_current(channel)
            limit = round(random.uniform(minimum_current_limit, maximum_current_limit), 4)
            self.psut.set_current_limit(channel, limit)
            read_limit = self.psut.get_current_limit(channel)
            self.assertEqual(limit, read_limit)

    def test_measured_voltage(self):
        print("test_measured_voltage")
        available_channels = self.psut.get_available_channels()
        for x in range(10):
            channel = random.choice(available_channels)
            maximum_source_voltage = self.psut.get_maximum_source_voltage(channel)
            minimum_source_voltage = self.psut.get_minimum_source_voltage(channel)
            voltage = round(random.uniform(minimum_source_voltage, maximum_source_voltage), 4)
            self.psut.set_source_voltage(channel, voltage)
            self.psut.enable_output(channel)
            for aux_channel in available_channels:
                if aux_channel == channel:
                    self.assertTrue(self.psut.is_output_enabled(aux_channel))
                else:
                    self.assertFalse(self.psut.is_output_enabled(aux_channel))

            read_voltage = self.psut.get_measured_voltage(channel)
            self.psut.disable_output(channel)
            self.assertAlmostEqual(voltage, read_voltage, 1)

    def test_all_measured_voltages(self):
        print("test_all_measured_voltages")
        available_channels = self.psut.get_available_channels()
        for x in range(10):
            voltages = []
            for channel in available_channels:
                maximum_source_voltage = self.psut.get_maximum_source_voltage(channel)
                minimum_source_voltage = self.psut.get_minimum_source_voltage(channel)
                voltage = round(random.uniform(minimum_source_voltage, maximum_source_voltage), 4)
                voltages.append(voltage)
            self.psut.set_all_source_voltages(voltages)
            self.psut.enable_all_outputs()
            for aux_channel in available_channels:
                self.assertTrue(self.psut.is_output_enabled(aux_channel))

            read_voltages = self.psut.get_all_measured_voltages()
            self.psut.disable_all_outputs()
            for index in range(0, len(available_channels)):
                self.assertAlmostEqual(voltages[index], read_voltages[index], 1)

    def test_measured_current(self):
        print("test_measured_current")
        # This test require a resistor (recommended 1kOhm) in channel 1
        resistance = 1000
        for x in range(10):
            channel = 1
            maximum_source_voltage = self.psut.get_maximum_source_voltage(channel)
            voltage = round(random.uniform(maximum_source_voltage / 2, maximum_source_voltage), 4)
            self.psut.set_source_voltage(channel, voltage)
            self.psut.enable_output(channel)
            time.sleep(1)
            read_current = self.psut.get_measured_current(channel)
            self.psut.disable_output(channel)
            self.assertAlmostEqual(voltage / resistance, read_current, 2)

    def test_all_measured_currents(self):
        print("test_all_measured_currents")
        # This test require a resistor (recommended 1kOhm) in channel 1
        available_channels = self.psut.get_available_channels()
        resistance = 1000
        for x in range(10):
            maximum_source_voltage = self.psut.get_maximum_source_voltage(1)
            minimum_source_voltage = self.psut.get_minimum_source_voltage(1)
            voltage = round(random.uniform(minimum_source_voltage, maximum_source_voltage), 4)
            voltages = [voltage, 0, 0]
            self.psut.set_all_source_voltages(voltages)
            self.psut.enable_all_outputs()
            time.sleep(1)
            for aux_channel in available_channels:
                self.assertTrue(self.psut.is_output_enabled(aux_channel))

            read_currents = self.psut.get_all_measured_currents()
            self.psut.disable_all_outputs()
            for index in range(0, len(available_channels)):
                self.assertAlmostEqual(voltages[index] / resistance, read_currents[index], 2)

    def test_measured_power(self):
        print("test_measured_power")
        # This test require a resistor (recommended 1kOhm) in channel 1
        resistance = 1000
        for x in range(10):
            channel = 1
            maximum_source_voltage = self.psut.get_maximum_source_voltage(channel)
            voltage = round(random.uniform(maximum_source_voltage / 2, maximum_source_voltage), 4)
            self.psut.set_source_voltage(channel, voltage)
            self.psut.enable_output(channel)
            time.sleep(1)
            read_power = self.psut.get_measured_power(channel)
            self.psut.disable_output(channel)
            self.assertAlmostEqual(voltage**2 / resistance, read_power, 1)

    def test_all_measured_powers(self):
        print("test_all_measured_powers")
        # This test require a resistor (recommended 1kOhm) in channel 1
        available_channels = self.psut.get_available_channels()
        resistance = 1000
        for x in range(10):
            maximum_source_voltage = self.psut.get_maximum_source_voltage(1)
            minimum_source_voltage = self.psut.get_minimum_source_voltage(1)
            voltage = round(random.uniform(minimum_source_voltage, maximum_source_voltage), 4)
            voltages = [voltage, 0, 0]
            self.psut.set_all_source_voltages(voltages)
            self.psut.enable_all_outputs()
            time.sleep(1)
            for aux_channel in available_channels:
                self.assertTrue(self.psut.is_output_enabled(aux_channel))

            read_powers = self.psut.get_all_measured_powers()
            self.psut.disable_all_outputs()
            for index in range(0, len(available_channels)):
                self.assertAlmostEqual(voltages[index]**2 / resistance, read_powers[index], 1)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
