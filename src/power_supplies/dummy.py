import random
from power_supply import PowerSupply


class Dummy(PowerSupply):
    def __init__(self, port, number_channels=2):
        self.voltages = [0] * number_channels
        self.currents = [0] * number_channels
        self.voltage_limits = [0] * number_channels
        self.current_limits = [0] * number_channels
        self.channels = list(range(1, number_channels + 1))
        self.dummy_output_enabled = [False] * number_channels
        self.dummy_series_mode_enabled = False
        self.dummy_parallel_mode_enabled = False
        self.maximum_source_current = [5] * number_channels
        self.minimum_source_current = [0.01] * number_channels
        self.maximum_source_voltage = [30] * number_channels
        self.minimum_source_voltage = [0] * number_channels
        self.voltage_error = 0.1
        self.current_error = 0.05

    def reset(self):
        print("Dummy PSU resetted")

    def get_version(self):
        return "Dummy"

    def get_available_channels(self):
        return self.channels

    def check_channel(self, channel):
        assert channel in self.channels or channel in [str(x) for x in self.channels], f"Wrong channel index: {channel}"
        return channel - 1

    def enable_output(self, channel):
        channel = self.check_channel(channel)
        self.dummy_output_enabled[channel] = True
        self.currents[channel] = random.uniform(self.minimum_source_current[channel], self.current_limits[channel])
        return True

    def is_output_enabled(self, channel):
        channel = self.check_channel(channel)
        return self.dummy_output_enabled[channel]

    def enable_all_outputs(self):
        for channel in self.channels:
            self.dummy_output_enabled[channel] = True
            self.currents[channel] = random.uniform(self.minimum_source_current[channel], self.current_limits[channel])
        return True

    def is_series_mode_enabled(self):
        return self.dummy_series_mode_enabled

    def enable_series_mode(self):
        self.dummy_series_mode_enabled = True
        return True

    def disable_series_mode(self):
        self.dummy_series_mode_enabled = False
        return True

    def is_parallel_mode_enabled(self):
        return self.dummy_parallel_mode_enabled

    def enable_parallel_mode(self):
        self.dummy_parallel_mode_enabled = True
        return True

    def disable_parallel_mode(self):
        self.dummy_parallel_mode_enabled = False
        return True

    def disable_output(self, channel):
        channel = self.check_channel(channel)
        self.dummy_output_enabled[channel] = False
        self.currents[channel] = 0
        return True

    def disable_all_outputs(self):
        for channel in self.channels:
            self.dummy_output_enabled[channel] = False
            self.currents[channel] = 0
        return True

    def set_all_source_voltages(self, voltages):
        self.voltages = voltages
        return True

    def set_source_voltage(self, channel, voltage):
        channel = self.check_channel(channel)
        self.voltages[channel] = voltage
        return True

    def get_all_source_voltages(self):
        return self.voltages

    def get_source_voltage(self, channel):
        channel = self.check_channel(channel)
        return self.get_all_source_voltages()[channel]

    def set_current_limit(self, channel, limit):
        channel = self.check_channel(channel)
        return self.voltages[channel]

    def get_current_limit(self, channel):
        channel = self.check_channel(channel)
        return self.current_limits[channel]

    def get_maximum_source_current(self, channel=1):
        channel = self.check_channel(channel)
        return self.maximum_source_current[channel]

    def get_minimum_source_current(self, channel=1):
        channel = self.check_channel(channel)
        return self.minimum_source_current[channel]

    def set_voltage_limit(self, channel, limit):
        channel = self.check_channel(channel)
        self.voltage_limits[channel] = limit
        return True

    def get_voltage_limit(self, channel):
        channel = self.check_channel(channel)
        return self.voltage_limits[channel]

    def get_maximum_source_voltage(self, channel=1):
        channel = self.check_channel(channel)
        return self.maximum_source_voltage[channel]

    def get_minimum_source_voltage(self, channel=1):
        channel = self.check_channel(channel)
        return self.minimum_source_voltage[channel]

    def get_measured_voltage(self, channel):
        channel = self.check_channel(channel)
        return self.voltages[channel] * (1 + random.uniform(-self.voltage_error, self.voltage_error))

    def get_all_measured_voltages(self):
        return [x * (1 + random.uniform(-self.voltage_error, self.voltage_error)) for x in self.voltages]

    def get_measured_current(self, channel):
        channel = self.check_channel(channel)
        return self.currents[channel] * (1 + random.uniform(-self.current_error, self.current_error))

    def get_all_measured_currents(self):
        return [x * (1 + random.uniform(-self.current_error, self.current_error)) for x in self.currents]

    def get_measured_power(self, channel):
        channel = self.check_channel(channel)
        return self.currents[channel] * (1 + random.uniform(-self.current_error, self.current_error)) * self.voltages[channel] * (1 + random.uniform(-self.voltage_error, self.voltage_error))

    def get_all_measured_powers(self):
        return [x * (1 + random.uniform(-self.current_error, self.current_error)) * self.voltages[i] * (1 + random.uniform(-self.voltage_error, self.voltage_error)) for i, x in enumerate(self.currents)]
