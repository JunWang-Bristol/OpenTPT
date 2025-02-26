
class PowerSupply():
    def factory(name, port):
        if name == "BK9129B":
            from power_supplies.BK import BK9129B
            return BK9129B(port)

    def check_channel_index(self, channel_index):
        raise NotImplementedError

    def reset(self):
        raise NotImplementedError

    def get_version(self, channel_index):
        raise NotImplementedError

    def get_available_channels(self, channel_index):
        raise NotImplementedError

    def enable_output(self, channel_index):
        raise NotImplementedError

    def enable_all_outputs(self):
        raise NotImplementedError

    def is_output_enabled(self, channel_index):
        raise NotImplementedError

    def disable_output(self, channel_index):
        raise NotImplementedError

    def disable_all_outputs(self):
        raise NotImplementedError

    def set_all_source_voltages(self, voltages):
        raise NotImplementedError

    def set_source_voltage(self, channel_index, voltage):
        self.check_channel_index(channel_index)
        self.voltages[channel_index] = voltage
        return self.set_all_source_voltages(self.voltages)

    def get_all_source_voltages(self):
        raise NotImplementedError

    def get_source_voltage(self, channel_index):
        self.check_channel_index(channel_index)
        return self.get_all_source_voltages()[channel_index]

    def set_current_limit(self, channel_index, limit):
        raise NotImplementedError

    def get_current_limit(self, channel_index):
        raise NotImplementedError

    def get_maximum_source_current(self, channel_index=1):
        raise NotImplementedError

    def get_minimum_source_current(self, channel_index=1):
        raise NotImplementedError

    def set_voltage_limit(self, channel_index, limit):
        raise NotImplementedError

    def get_voltage_limit(self, channel_index):
        raise NotImplementedError

    def get_maximum_source_voltage(self, channel_index=1):
        raise NotImplementedError

    def get_minimum_source_voltage(self, channel_index=1):
        raise NotImplementedError

    def get_measured_voltage(self, channel_index):
        raise NotImplementedError

    def get_all_measured_voltages(self):
        raise NotImplementedError

    def get_measured_current(self, channel_index):
        raise NotImplementedError

    def get_all_measured_currents(self):
        raise NotImplementedError

    def get_measured_power(self, channel_index):
        raise NotImplementedError

    def get_all_measured_powers(self):
        raise NotImplementedError

    def reset_limits(self):
        for channel in self.get_available_channels():
            self.set_current_limit(channel, self.get_maximum_source_current(channel))
            self.set_voltage_limit(channel, self.get_maximum_source_voltage(channel))
