import re
import ctypes
from picosdk.ps2000a import ps2000a as ps
from oscilloscope import Oscilloscope
from picosdk.functions import adc2mV, assert_pico_ok


class PicoScope(Oscilloscope):

    class ChannelInfo():
        def __init__(self, index, input_voltage_range, coupling, analog_offset):
            self.index = index
            self.enabled = True
            self.input_voltage_range = input_voltage_range
            self.coupling = coupling
            self.analog_offset = analog_offset

        def is_valid(self):
            return self.coupling is not None and self.input_voltage_range is not None and self.analog_offset

        def enable(self):
            self.enabled = True

        def disable(self):
            self.enabled = False

    def __init__(self, port):
        self.chandle = ctypes.c_int16()
        status = {}
        status["openunit"] = ps.ps2000aOpenUnit(ctypes.byref(self.chandle), None)
        self.channel_info = {}

        max_offset = ctypes.c_float(0)
        min_offset = ctypes.c_float(0)

        assert_pico_ok(status["openunit"])

    def get_number_channels(self):
        return ps.PS2000A_CHANNEL['PS2000A_MAX_CHANNELS']

    def get_status(self, status_code):
        for key, value in ps.PICO_STATUS.items():
            if status_code == value:
                return key

    def get_channel_index(self, channel_name):
        for key, value in ps.PS2000A_CHANNEL.items():
            if channel_name in key:
                return value

    def get_input_voltage_ranges(self):
        # First and last one is outside the device's range
        return list(ps.PICO_VOLTAGE_RANGE.values())[1:-1]

    def get_analog_offset_range(self, coupling, input_voltage_range):
        max_offset = ctypes.c_float(0)
        min_offset = ctypes.c_float(0)
        status = self.get_status(ps.ps2000aGetAnalogueOffset(self.chandle, self.get_input_voltage_index(input_voltage_range), coupling, ctypes.byref(max_offset), ctypes.byref(min_offset)))
        if status != 'PICO_OK':
            raise Exception(f"Something went wrong with ps2000aGetAnalogueOffset method: {status}")

        return [min_offset.value, max_offset.value]

    def get_input_voltage_index(self, input_voltage_range_str_or_float):
        if isinstance(input_voltage_range_str_or_float, str):
            if input_voltage_range_str_or_float == 'PS2000A_10MV' or input_voltage_range_str_or_float == 'PS2000A_50V':
                raise Exception(f"{input_voltage_range_str_or_float} not included for PicoScope 2408B")
            return ps.PS2000A_RANGE[input_voltage_range_str_or_float]
        elif isinstance(input_voltage_range_str_or_float, float):
            if input_voltage_range_str_or_float == 0.01 or input_voltage_range_str_or_float == 50:
                raise Exception(f"{input_voltage_range_str_or_float} not included for PicoScope 2408B")
            for key, value in ps.PICO_VOLTAGE_RANGE.items():
                if input_voltage_range_str_or_float == value:
                    return key
            else:
                raise Exception(f"{input_voltage_range_str_or_float} not in {self.get_input_voltage_ranges}")
        else:
            raise Exception(f"{input_voltage_range_str_or_float} should be a float or string")

    def set_channel_configuration(self, channel_index, input_voltage_range, coupling, analog_offset, enable=True):
        self.check_channel_index(channel_index)

        [minimum_analog_offset_range, maximum_analog_offset_range] = self.get_analog_offset_range(coupling, input_voltage_range)
        if not minimum_analog_offset_range < analog_offset < maximum_analog_offset_range:
            raise Exception(f"Analog offset {analog_offset} is not between limits for input voltage range {input_voltage_range}: [{minimum_analog_offset_range}, {maximum_analog_offset_range}]")

        status = ps.ps2000aSetChannel(self.chandle, channel_index, 1 if enable else 0, coupling, self.get_input_voltage_index(input_voltage_range), analog_offset)
        assert_pico_ok(status)
        self.channel_info[channel_index] = self.ChannelInfo(channel_index, input_voltage_range, coupling, analog_offset)
        return True

    def get_channel_configuration(self, channel_index):
        self.check_channel_index(channel_index)

        if channel_index not in self.channel_info:
            raise Exception(f"Channel {channel_index} has not been configured yet")
        return self.channel_info[channel_index]

    def enable_channel(self, channel_index):
        self.check_channel_index(channel_index)

        if channel_index not in self.channel_info:
            raise Exception(f"Channel {channel_index} has not been configured yet")
        status = ps.ps2000aSetChannel(self.chandle, channel_index, 1, self.channel_info[channel_index].coupling, self.get_input_voltage_index(self.channel_info[channel_index].input_voltage_range), self.channel_info[channel_index].analog_offset)
        assert_pico_ok(status)

    def disable_channel(self, channel_index):
        self.check_channel_index(channel_index)

        if channel_index not in self.channel_info:
            raise Exception(f"Channel {channel_index} has not been configured yet")
        status = ps.ps2000aSetChannel(self.chandle, channel_index, 0, self.channel_info[channel_index].coupling, self.get_input_voltage_index(self.channel_info[channel_index].input_voltage_range), self.channel_info[channel_index].analog_offset)
        assert_pico_ok(status)

    def check_channel_index(self, channel_index):
        if channel_index >= self.get_number_channels():
            raise Exception(f"Channel {channel_index} does not exist on this device")

    def reset(self):
        raise NotImplementedError

    def get_version(self, channel_index):
        raise NotImplementedError


class PicoScope2408B(PicoScope):
    def __init__(self, port):
        super().__init__(port)
