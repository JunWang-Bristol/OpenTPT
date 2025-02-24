import re
import ctypes
from picosdk.ps2000a import ps2000a as ps
from oscilloscope import Oscilloscope
from picosdk.functions import adc2mV, mV2adc, assert_pico_ok


class PicoScope(Oscilloscope):

    class ChannelInfo():
        def __init__(self, index, input_voltage_range, coupling, analog_offset):
            self.index = index
            self.enabled = True
            self.input_voltage_range = input_voltage_range
            self.coupling = coupling
            self.analog_offset = analog_offset

        def enable(self):
            self.enabled = True

        def disable(self):
            self.enabled = False

    class TriggerInfo():
        def __init__(self, index, threshold_voltage, direction, delayed_samples, timeout):
            self.index = index
            self.enabled = True
            self.threshold_voltage = threshold_voltage
            self.direction = direction
            self.delayed_samples = delayed_samples
            self.timeout = timeout

        def enable(self):
            self.enabled = True

        def disable(self):
            self.enabled = False

    def __init__(self, port):
        self.handle = ctypes.c_int16()
        status = {}

        # Don't ask...
        ps.make_symbol("_ApplyFix", "ps2000aApplyFix", ctypes.c_uint32, [ctypes.c_int32, ctypes.c_int16], "PICO_STATUS ps2000aApplyFix ( int32_t fixNo, int16_t value );")
        status["ApplyFix"] = ps.ps2000aApplyFix(0x421ced9168, 0x1420011e6)

        status["openunit"] = ps.ps2000aOpenUnit(ctypes.byref(self.handle), None)
        self.channel_info = {}
        self.trigger_info = {}
        self.number_segments = 1

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
        status = self.get_status(ps.ps2000aGetAnalogueOffset(self.handle, self.get_input_voltage_index(input_voltage_range), coupling, ctypes.byref(max_offset), ctypes.byref(min_offset)))
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

    def set_channel_configuration(self, channel, input_voltage_range, coupling, analog_offset, enable=True):
        channel_index = self.check_channel(channel)

        [minimum_analog_offset_range, maximum_analog_offset_range] = self.get_analog_offset_range(coupling, input_voltage_range)
        if not minimum_analog_offset_range < analog_offset < maximum_analog_offset_range:
            raise Exception(f"Analog offset {analog_offset} is not between limits for input voltage range {input_voltage_range}: [{minimum_analog_offset_range}, {maximum_analog_offset_range}]")

        status = ps.ps2000aSetChannel(self.handle, channel_index, 1 if enable else 0, coupling, self.get_input_voltage_index(input_voltage_range), analog_offset)
        assert_pico_ok(status)
        self.channel_info[channel_index] = self.ChannelInfo(channel_index, input_voltage_range, coupling, analog_offset)
        return True

    def get_channel_configuration(self, channel):
        channel_index = self.check_channel(channel)

        if channel_index not in self.channel_info:
            raise Exception(f"Channel {channel_index} has not been configured yet")
        return self.channel_info[channel_index]

    def enable_channel(self, channel):
        channel_index = self.check_channel(channel)

        if channel_index not in self.channel_info:
            raise Exception(f"Channel {channel_index} has not been configured yet")
        status = ps.ps2000aSetChannel(self.handle, channel_index, 1, self.channel_info[channel_index].coupling, self.get_input_voltage_index(self.channel_info[channel_index].input_voltage_range), self.channel_info[channel_index].analog_offset)
        assert_pico_ok(status)

    def disable_channel(self, channel):
        channel_index = self.check_channel(channel)

        if channel_index not in self.channel_info:
            raise Exception(f"Channel {channel_index} has not been configured yet")
        status = ps.ps2000aSetChannel(self.handle, channel_index, 0, self.channel_info[channel_index].coupling, self.get_input_voltage_index(self.channel_info[channel_index].input_voltage_range), self.channel_info[channel_index].analog_offset)
        assert_pico_ok(status)

    def check_channel(self, channel):
        if isinstance(channel, str):
            if channel in ["0", "1", "2", "3"]:
                return int(channel)
            elif channel == "A":
                return 0
            elif channel == "B":
                return 1
            elif channel == "C":
                return 2
            elif channel == "D":
                return 3
            else:
                raise Exception(f"Channel {channel} does not exist on this device")
        elif isinstance(channel, float):
            return self.check_channel(int(channel))
        elif isinstance(channel, int):
            if channel < 0 or channel >= self.get_number_channels():
                raise Exception(f"Channel {channel} does not exist on this device")
            return channel
        else:
            raise Exception(f"Channel {channel} does not exist on this device")

    def get_maximum_ADC_count(self):
        maxADC = ctypes.c_int16(0)
        ps.ps2000aMaximumValue(self.handle, ctypes.byref(maxADC))
        return maxADC.value

    def get_minimum_ADC_count(self):
        minADC = ctypes.c_int16(0)
        ps.ps2000aMinimumValue(self.handle, ctypes.byref(minADC))
        return minADC.value

    def set_trigger(self, channel, threshold_voltage, direction, delayed_samples=0, timeout=5000, enable=True):
        channel_index = self.check_channel(channel)

        input_voltage_range = self.get_channel_configuration(channel_index).input_voltage_range

        threshold_adc_count = round(threshold_voltage / input_voltage_range * self.get_maximum_ADC_count())
        status = ps.ps2000aSetSimpleTrigger(self.handle, 
                                            1 if enable else 0,
                                            channel_index,
                                            threshold_adc_count,
                                            direction,
                                            delayed_samples,
                                            timeout)
        assert_pico_ok(status)
        self.trigger_info[channel_index] = self.TriggerInfo(channel_index, threshold_voltage, direction, delayed_samples, timeout)

    def set_rising_trigger(self, channel, threshold_voltage, delayed_samples=0, timeout=5000):
        self.set_trigger(channel, threshold_voltage, ps.PS2000A_THRESHOLD_DIRECTION['PS2000A_RISING'], delayed_samples, timeout, True)

    def set_falling_trigger(self, channel, threshold_voltage, delayed_samples=0, timeout=5000):
        self.set_trigger(channel, threshold_voltage, ps.PS2000A_THRESHOLD_DIRECTION['PS2000A_FALLING'], delayed_samples, timeout, True)

    def get_trigger_configuration(self, channel):
        channel_index = self.check_channel(channel)

        if channel_index not in self.trigger_info:
            raise Exception(f"Trigger for channel {channel_index} has not been configured yet")
        return self.trigger_info[channel_index]

    def arm_trigger(self, channel):
        channel_index = self.check_channel(channel)
        info = self.trigger_info[channel_index]
        self.set_trigger(channel, info.threshold_voltage, info.direction, info.delayed_samples, info.timeout, True)

    def disarm_trigger(self, channel):
        channel_index = self.check_channel(channel)
        info = self.trigger_info[channel_index]
        self.set_trigger(channel, info.threshold_voltage, info.direction, info.delayed_samples, info.timeout, False)

    def is_trigger_armed(self):
        trigger_enabled = ctypes.c_int16(0)
        pulse_width_qualifier_enabled = ctypes.c_int16(0)
        status = ps.ps2000aIsTriggerOrPulseWidthQualifierEnabled(self.handle, ctypes.byref(trigger_enabled), ctypes.byref(pulse_width_qualifier_enabled))
        assert_pico_ok(status)
        return trigger_enabled.value != 0

    def set_number_segments(self, number_segments):
        maximum_samples = ctypes.c_uint16(0)
        status = ps.ps2000aMemorySegments(self.handle, number_segments, ctypes.byref(maximum_samples))
        assert_pico_ok(status)
        self.number_segments = number_segments
        return maximum_samples.value

    def get_number_segments(self):
        return self.number_segments

    def get_maximum_samples(self):
        maximum_samples = ctypes.c_uint16(0)
        status = ps.ps2000aMemorySegments(self.handle, self.number_segments, ctypes.byref(maximum_samples))
        assert_pico_ok(status)
        return maximum_samples.value

    # 2408B specific    
    def convert_time_to_timebase(self, time):
        if time > 34.35973836:
            raise Exception(f"Too much time: {time} seconds. Maximum supported: 34.35973836 seconds")
        if time <= 1e-9:
            return 0
        elif time <= 2e-9:
            return 1
        elif time <= 4e-9:
            return 2
        else:
            return int(time * 125000000 + 2)

    # 2408B specific        
    def convert_timebase_to_time(self, timebase):
        if timebase > 2**32 - 1:
            raise Exception(f"Too much timebase: {timebase} seconds. Maximum supported: {2**32 - 1}")
        if timebase == 0:
            return 1e-9
        elif timebase == 1:
            return 2e-9
        elif timebase == 2:
            return 4e-9
        else:
            return (timebase - 2) / 125000000

    def get_real_sampling_time(self, desired_time, desired_number_samples):
        timebase = self.convert_time_to_timebase(desired_time)
        time_interval_ns = ctypes.c_float()
        maximum_samples = ctypes.c_int32()
        assert self.number_segments == 1, "Only one segment supported for now"
        status = ps.ps2000aGetTimebase2(self.handle,
                                        timebase,
                                        desired_number_samples,
                                        ctypes.byref(time_interval_ns),
                                        0,
                                        ctypes.byref(maximum_samples),
                                        0)
        assert_pico_ok(status)
        return time_interval_ns.value * 1e-9

    def run_acquisition_block(self, sampling_time, number_samples=None):
        if number_samples is None:
            number_samples = self.get_maximum_samples()
        timebase = self.convert_time_to_timebase(sampling_time)
        aux = round(number_samples * 0.01)  # hardcoded
        number_pre_trigger_samples = ctypes.c_int32(aux)
        number_post_trigger_samples = ctypes.c_int32(number_samples - aux)

        status = ps.ps2000aRunBlock(self.handle,
                                    number_pre_trigger_samples,
                                    number_post_trigger_samples,
                                    timebase,
                                    0,
                                    None,
                                    0,
                                    None,
                                    None)
        assert_pico_ok(status)
        return True

    def read_data(self, channel, number_samples=None):
        if number_samples is None:
            number_samples = self.get_maximum_samples()
        channel_index = self.check_channel(channel)
        print("number_samples")
        print(number_samples)
        print("channel_index")
        print(channel_index)

        ready = ctypes.c_int16(0)
        while ready.value == 0:
            status = ps.ps2000aIsReady(self.handle, ctypes.byref(ready))
        assert_pico_ok(status)

        buffer = (ctypes.c_int16 * number_samples)()
        status = ps.ps2000aSetDataBuffers(self.handle,
                                          channel_index,
                                          ctypes.byref(buffer),
                                          None,
                                          number_samples,
                                          0,
                                          ps.PS2000A_RATIO_MODE['PS2000A_RATIO_MODE_NONE'])

        return True


class PicoScope2408B(PicoScope):
    def __init__(self, port):
        super().__init__(port)
