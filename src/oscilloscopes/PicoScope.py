from scipy import interpolate
import numpy
import pandas
import math
import ctypes
from picosdk.ps2000a import ps2000a as ps2
from picosdk.ps3000a import ps3000a as ps3
from picosdk.ps6000 import ps6000 as ps6
from oscilloscope import Oscilloscope
from picosdk.functions import assert_pico_ok
from collections import deque


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

    def __init__(self, port, strict=False):
        self.handle = ctypes.c_int16()
        self.strict = strict

        status = self._open_unit(ctypes.byref(self.handle), None)
        assert_pico_ok(status)

        self.channel_info = {}
        self.trigger_info = {}
        self.number_segments = 1
        self.number_samples = int(self.get_maximum_samples())
        self.sampling_time = 4e-9
        self.number_pre_trigger_samples = 0
        self.upsampling_scale = 1
        self.upsampled_sampling_time = self.sampling_time

        self.channel_labels = {}
        self.channel_skew = {}
        for channel in self._get_channels():
            channel_index = self.check_channel(channel)
            self.channel_labels[channel_index] = channel
            self.channel_skew[channel_index] = 0

    def set_number_pre_trigger_samples(self, number_pre_trigger_samples):
        self.number_pre_trigger_samples = number_pre_trigger_samples

    def get_number_pre_trigger_samples(self):
        return self.number_pre_trigger_samples

    def get_number_upsampled_pre_trigger_samples(self):
        return self.number_pre_trigger_samples * self.upsampling_scale

    def set_number_samples(self, number_samples):
        self.number_samples = number_samples

    def get_number_samples(self):
        return self.number_samples

    def get_upsampling_scale(self):
        return self.upsampling_scale

    def get_upsampled_sampling_time(self):
        return self.upsampled_sampling_time

    def set_sampling_time(self, desired_sampling_time):
        real_sampling_time = self.get_real_sampling_time(desired_sampling_time)
        self.sampling_time = real_sampling_time
        return real_sampling_time

    def get_sampling_time(self):
        return self.sampling_time

    def set_channel_skew(self, channel, skew):
        channel_index = self.check_channel(channel)
        self.channel_skew[channel_index] = skew

    def get_channel_skew(self, channel):
        channel_index = self.check_channel(channel)
        return self.channel_skew[channel_index]

    @staticmethod
    def _get_channels_max():
        raise NotImplementedError

    @staticmethod
    def _get_channels():
        raise NotImplementedError

    @staticmethod
    def _get_status():
        raise NotImplementedError

    @staticmethod
    def _voltage_ranges():
        raise NotImplementedError

    @staticmethod
    def _ranges():
        raise NotImplementedError

    @staticmethod
    def _threshold_directions():
        raise NotImplementedError

    @staticmethod
    def _threshold_direction_rising():
        raise NotImplementedError

    @staticmethod
    def _threshold_direction_falling():
        raise NotImplementedError

    @staticmethod
    def _ratio_modes_none():
        raise NotImplementedError

    @staticmethod
    def _ratio_modes():
        raise NotImplementedError

    @staticmethod
    def _open_unit(status, serial):
        raise NotImplementedError

    @staticmethod
    def _get_analogue_offset(handle, range, coupling, maximumVoltage, minimumVoltage):
        raise NotImplementedError

    @staticmethod
    def _set_channel(handle, channel, enabled, type, range, analogOffset):
        raise NotImplementedError

    @staticmethod
    def _maximum_value(handle, value):
        raise NotImplementedError

    @staticmethod
    def _minimum_value(handle, value):
        raise NotImplementedError

    @staticmethod
    def _set_simple_trigger(handle, enable, source, threshold, direction, delay, autoTrigger_ms):
        raise NotImplementedError

    @staticmethod
    def _is_trigger_or_pulse_width_qualifier_enabled(handle, triggerEnabled, pulseWidthQualifierEnabled):
        raise NotImplementedError

    @staticmethod
    def _memory_segments(handle, nSegments, nMaxSamples):
        raise NotImplementedError

    @staticmethod
    def _get_timebase2(handle, timebase, noSamples, timeIntervalNanoseconds, oversample, totalSamples, segmentIndex):
        raise NotImplementedError

    @staticmethod
    def _run_block(handle, noOfPreTriggerSamples, noOfPostTriggerSamples, timebase, oversample, timeIndisposedMs, segmentIndex, lpReady, pParameter):
        raise NotImplementedError

    @staticmethod
    def _set_data_buffers(handle, channelOrPort, bufferMax, bufferMin, bufferLth, segmentIndex, mode):
        raise NotImplementedError

    @staticmethod
    def _is_ready(handle, ready):
        raise NotImplementedError

    @staticmethod
    def _get_values(handle, startIndex, noOfSamples, downSampleRatio, downSampleRatioMode, segmentIndex, overflow):
        raise NotImplementedError

    def get_number_channels(self):
        return self._get_channels_max()

    def get_status(self, status_code):
        for key, value in self._get_status().items():
            if status_code == value:
                return key

    def get_channel_index(self, channel_name):
        for key, value in enumerate(self._get_channels()):
            if channel_name in value:
                return key

    def get_input_voltage_ranges(self):
        raise NotImplementedError

    def get_analog_offset_range(self, coupling, input_voltage_range):
        max_offset = ctypes.c_float(0)
        min_offset = ctypes.c_float(0)
        status = self.get_status(self._get_analogue_offset(self.handle, self.get_input_voltage_index(input_voltage_range), coupling, ctypes.byref(max_offset), ctypes.byref(min_offset)))
        if status != 'PICO_OK':
            raise Exception(f"Something went wrong with _get_analogue_offset method: {status} with input_voltage_range: {input_voltage_range}")

        return [min_offset.value, max_offset.value]

    def get_input_voltage_index(self, input_voltage_range_str_or_float):
        raise NotImplementedError

    def set_channel_configuration(self, channel, input_voltage_range, coupling, analog_offset, enable=True):
        channel_index = self.check_channel(channel)
        self.channel_labels[channel_index] = channel

        input_voltage_range = self.check_input_voltage_range(input_voltage_range)

        [minimum_analog_offset_range, maximum_analog_offset_range] = self.get_analog_offset_range(coupling, input_voltage_range)
        if not minimum_analog_offset_range < analog_offset < maximum_analog_offset_range:
            raise Exception(f"Analog offset {analog_offset} is not between limits for input voltage range {input_voltage_range}: [{minimum_analog_offset_range}, {maximum_analog_offset_range}]")

        status = self._set_channel(self.handle, channel_index, 1 if enable else 0, coupling, self.get_input_voltage_index(input_voltage_range), analog_offset)
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
        status = self._set_channel(self.handle, channel_index, 1, self.channel_info[channel_index].coupling, self.get_input_voltage_index(self.channel_info[channel_index].input_voltage_range), self.channel_info[channel_index].analog_offset)
        assert_pico_ok(status)

    def disable_channel(self, channel):
        channel_index = self.check_channel(channel)

        if channel_index not in self.channel_info:
            raise Exception(f"Channel {channel_index} has not been configured yet")
        status = self._set_channel(self.handle, channel_index, 0, self.channel_info[channel_index].coupling, self.get_input_voltage_index(self.channel_info[channel_index].input_voltage_range), self.channel_info[channel_index].analog_offset)
        assert_pico_ok(status)

    def check_channel(self, channel):
        if isinstance(channel, str):
            if "_CHANNEL_" in channel:
                channel = channel.split("_CHANNEL_")[1]
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

    def check_input_voltage_range(self, input_voltage_range):

        if isinstance(input_voltage_range, int):
            input_voltage_range = float(input_voltage_range)

        if input_voltage_range not in self.get_input_voltage_ranges():
            if self.strict:
                raise Exception(f"Input voltage range {input_voltage_range} must be one of {self.get_input_voltage_ranges()}")
            else:
                for voltage in self.get_input_voltage_ranges():
                    if voltage > input_voltage_range:
                        input_voltage_range = voltage
                        break
                else:
                    input_voltage_range = self.get_input_voltage_ranges()[-1]

        return input_voltage_range

    def set_channel_label(self, channel, label):
        channel_index = self.check_channel(channel)
        self.channel_labels[channel_index] = label

    def get_maximum_ADC_count(self):
        maxADC = ctypes.c_int16(0)
        self._maximum_value(self.handle, ctypes.byref(maxADC))
        return maxADC.value

    def get_minimum_ADC_count(self):
        minADC = ctypes.c_int16(0)
        self._minimum_value(self.handle, ctypes.byref(minADC))
        return minADC.value

    def set_trigger(self, channel, threshold_voltage, direction, delayed_samples=0, timeout=0, enable=True):
        channel_index = self.check_channel(channel)

        input_voltage_range = self.get_channel_configuration(channel_index).input_voltage_range

        threshold_adc_count = round(threshold_voltage / input_voltage_range * self.get_maximum_ADC_count())
        status = self._set_simple_trigger(self.handle, 
                                          1 if enable else 0,
                                          channel_index,
                                          threshold_adc_count,
                                          direction,
                                          delayed_samples,
                                          timeout)
        assert_pico_ok(status)
        self.trigger_info[channel_index] = self.TriggerInfo(channel_index, threshold_voltage, direction, delayed_samples, timeout)

    def set_rising_trigger(self, channel, threshold_voltage, delayed_samples=0, timeout=0):
        self.set_trigger(channel, threshold_voltage, self._threshold_direction_rising(), delayed_samples, timeout, True)

    def set_falling_trigger(self, channel, threshold_voltage, delayed_samples=0, timeout=0):
        self.set_trigger(channel, threshold_voltage, self._threshold_direction_falling(), delayed_samples, timeout, True)

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
        status = self._is_trigger_or_pulse_width_qualifier_enabled(self.handle, ctypes.byref(trigger_enabled), ctypes.byref(pulse_width_qualifier_enabled))
        assert_pico_ok(status)
        return trigger_enabled.value != 0

    def set_number_segments(self, number_segments):
        maximum_samples = ctypes.c_uint16(0)
        status = self._memory_segments(self.handle, number_segments, ctypes.byref(maximum_samples))
        assert_pico_ok(status)
        self.number_segments = number_segments
        return maximum_samples.value

    def get_number_segments(self):
        return self.number_segments

    def get_maximum_samples(self):
        maximum_samples = ctypes.c_uint16(0)
        status = self._memory_segments(self.handle, self.number_segments, ctypes.byref(maximum_samples))
        assert_pico_ok(status)
        return maximum_samples.value

    def convert_time_to_timebase(self, time):
        raise NotImplementedError

    def convert_timebase_to_time(self, timebase):
        raise NotImplementedError

    def get_real_sampling_time(self, desired_time=None, desired_number_samples=None):
        if desired_number_samples is None:
            desired_number_samples = self.number_samples

        if desired_time is None:
            desired_time = self.sampling_time

        desired_time = max(self.minimum_sampling_time, desired_time)
        timebase = self.convert_time_to_timebase(desired_time)
        time_interval_ns = ctypes.c_float()
        maximum_samples = ctypes.c_int32()
        assert self.number_segments == 1, "Only one segment supported for now"
        status = self._get_timebase2(self.handle,
                                     timebase,
                                     desired_number_samples,
                                     ctypes.byref(time_interval_ns),
                                     0,
                                     ctypes.byref(maximum_samples),
                                     0)
        real_sampling_time = time_interval_ns.value * 1e-9
        assert_pico_ok(status)
        return real_sampling_time

    def run_acquisition_block(self, sampling_time=None, number_samples=None):
        if number_samples is None:
            number_samples = self.number_samples

        if sampling_time is None:
            sampling_time = self.sampling_time

        timebase = self.convert_time_to_timebase(sampling_time)
        number_pre_trigger_samples = self.number_pre_trigger_samples
        number_post_trigger_samples = number_samples - self.number_pre_trigger_samples
        number_pre_trigger_samples = ctypes.c_int32(number_pre_trigger_samples)
        number_post_trigger_samples = ctypes.c_int32(number_post_trigger_samples)

        status = self._run_block(self.handle,
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

    def read_data(self, channels=None, number_samples=None, data_format="dataframe"):
        if number_samples is None:
            number_samples = self.number_samples

        if channels is None:
            channels = self.channel_info.keys()

        buffers = {}
        for channel in channels:
            channel_index = self.check_channel(channel)
            buffer = (ctypes.c_int16 * number_samples)()
            buffers[channel] = buffer
            status = self._set_data_buffers(self.handle,
                                            channel_index,
                                            ctypes.byref(buffer),
                                            None,
                                            number_samples,
                                            0,
                                            self._ratio_modes_none())

        ready = ctypes.c_int16(0)
        while ready.value == 0:
            status = self._is_ready(self.handle, ctypes.byref(ready))
        assert_pico_ok(status)

        overflow = ctypes.c_int16(0)
        number_samples_ctype = ctypes.c_uint32(number_samples)

        status = self._get_values(self.handle,
                                  0,
                                  ctypes.byref(number_samples_ctype),
                                  0,
                                  0,
                                  self._ratio_modes_none(),
                                  ctypes.byref(overflow))
        assert_pico_ok(status)

        gcd_samplig_time_and_skew = self.sampling_time
        for _, skew in self.channel_skew.items():
            if skew == 0:
                continue
            skew_in_ps = int(math.fabs(skew) * 1e12)
            gcd_samplig_time_and_skew_in_ps = int(math.fabs(gcd_samplig_time_and_skew) * 1e12)
            gcd_samplig_time_and_skew_in_ps = math.gcd(skew_in_ps, gcd_samplig_time_and_skew_in_ps)
            gcd_samplig_time_and_skew = float(gcd_samplig_time_and_skew_in_ps) / 1e12

        data = {}
        self.upsampling_scale = int(self.sampling_time / gcd_samplig_time_and_skew)
        self.upsampled_sampling_time = gcd_samplig_time_and_skew
        sampled_time_array = numpy.linspace(0, (number_samples - 1) * self.sampling_time, number_samples)
        data["data"] = {}
        data["time"] = numpy.linspace(0, (number_samples - 1) * self.sampling_time, int(number_samples * self.upsampling_scale))

        for channel in channels:
            channel_index = self.check_channel(channel)

            data_in_adc_count = numpy.array(buffers[channel])
            data_in_volts = data_in_adc_count / self.get_maximum_ADC_count() * self.get_channel_configuration(channel_index).input_voltage_range
            if gcd_samplig_time_and_skew != self.sampling_time:
                f = interpolate.interp1d(sampled_time_array, data_in_volts)
                data_in_volts = [f(x) for x in data["time"]]
                positions_to_rotate = int(self.channel_skew[channel_index] / gcd_samplig_time_and_skew)
                if positions_to_rotate != 0:
                    aux = deque(data_in_volts)
                    aux.rotate(positions_to_rotate)
                    data_in_volts = list(aux)

            data["data"][self.channel_labels[channel_index]] = data_in_volts

        if data_format == "dataframe":
            df = pandas.DataFrame()
            df["time"] = data["time"]
            for channel in channels:
                channel_index = self.check_channel(channel)
                df[self.channel_labels[channel_index]] = data["data"][self.channel_labels[channel_index]]
            data = df
        return data


class PicoScope2408B(PicoScope):
    def __init__(self, port, strict=False):        # Don't ask...
        status = {}

        ps2.make_symbol("_ApplyFix", "ps2000aApplyFix", ctypes.c_uint32, [ctypes.c_int32, ctypes.c_int16], "PICO_STATUS ps2000aApplyFix ( int32_t fixNo, int16_t value );")
        status["ApplyFix"] = ps2.ps2000aApplyFix(0x421ced9168, 0x1420011e6)
        self.minimum_sampling_time = 4e-9  # for 3 or 4 channels
        super().__init__(port, strict)

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

    def get_input_voltage_index(self, input_voltage_range_str_or_float):
        if isinstance(input_voltage_range_str_or_float, str):
            if input_voltage_range_str_or_float == 'PS2000A_10MV' or input_voltage_range_str_or_float == 'PS2000A_50V':
                raise Exception(f"{input_voltage_range_str_or_float} not included for PicoScope 2408B")
            return self._ranges()[input_voltage_range_str_or_float]
        elif isinstance(input_voltage_range_str_or_float, float):
            if input_voltage_range_str_or_float == 0.01 or input_voltage_range_str_or_float == 50:
                raise Exception(f"{input_voltage_range_str_or_float} not included for PicoScope 2408B")
            for key, value in self._voltage_ranges().items():
                if input_voltage_range_str_or_float == value:
                    return key
            else:
                raise Exception(f"{input_voltage_range_str_or_float} not in {self.get_input_voltage_ranges}")
        else:
            raise Exception(f"{input_voltage_range_str_or_float} should be a float or string")

    def get_input_voltage_ranges(self):
        # First and last one is outside the device's range
        return list(self._voltage_ranges().values())[1:-1]

    @staticmethod
    def _get_channels_max():
        return ps2.PS2000A_CHANNEL['PS2000A_MAX_CHANNELS']

    @staticmethod
    def _get_channels():
        return [x for x in ps2.PS2000A_CHANNEL if "_CHANNEL_" in x]

    @staticmethod
    def _get_status():
        return ps2.PICO_STATUS

    @staticmethod
    def _voltage_ranges():
        return ps2.PICO_VOLTAGE_RANGE

    @staticmethod
    def _ranges():
        return ps2.PS2000A_RANGE

    @staticmethod
    def _threshold_directions():
        return ps2.PS2000A_THRESHOLD_DIRECTION

    @staticmethod
    def _threshold_direction_rising():
        return ps2.PS2000A_THRESHOLD_DIRECTION['PS2000A_RISING']

    @staticmethod
    def _threshold_direction_falling():
        return ps2.PS2000A_THRESHOLD_DIRECTION['PS2000A_FALLING']

    @staticmethod
    def _ratio_modes_none():
        return ps2.PS2000A_RATIO_MODE['PS2000A_RATIO_MODE_NONE']

    @staticmethod
    def _ratio_modes():
        return ps2.PS2000A_RATIO_MODE

    @staticmethod
    def _open_unit(status, serial):
        return ps2.ps2000aOpenUnit(status, serial)

    @staticmethod
    def _get_analogue_offset(handle, range, coupling, maximumVoltage, minimumVoltage):
        return ps2.ps2000aGetAnalogueOffset(handle, range, coupling, maximumVoltage, minimumVoltage)

    @staticmethod
    def _set_channel(handle, channel, enabled, type, range, analogOffset):
        return ps2.ps2000aSetChannel(handle, channel, enabled, type, range, analogOffset)

    @staticmethod
    def _maximum_value(handle, value):
        return ps2.ps2000aMaximumValue(handle, value)

    @staticmethod
    def _minimum_value(handle, value):
        return ps2.ps2000aMinimumValue(handle, value)

    @staticmethod
    def _set_simple_trigger(handle, enable, source, threshold, direction, delay, autoTrigger_ms):
        return ps2.ps2000aSetSimpleTrigger(handle, enable, source, threshold, direction, delay, autoTrigger_ms)

    @staticmethod
    def _is_trigger_or_pulse_width_qualifier_enabled(handle, triggerEnabled, pulseWidthQualifierEnabled):
        return ps2.ps2000aIsTriggerOrPulseWidthQualifierEnabled(handle, triggerEnabled, pulseWidthQualifierEnabled)

    @staticmethod
    def _memory_segments(handle, nSegments, nMaxSamples):
        return ps2.ps2000aMemorySegments(handle, nSegments, nMaxSamples)

    @staticmethod
    def _get_timebase2(handle, timebase, noSamples, timeIntervalNanoseconds, oversample, totalSamples, segmentIndex):
        return ps2.ps2000aGetTimebase2(handle, timebase, noSamples, timeIntervalNanoseconds, oversample, totalSamples, segmentIndex)

    @staticmethod
    def _run_block(handle, noOfPreTriggerSamples, noOfPostTriggerSamples, timebase, oversample, timeIndisposedMs, segmentIndex, lpReady, pParameter):
        return ps2.ps2000aRunBlock(handle, noOfPreTriggerSamples, noOfPostTriggerSamples, timebase, oversample, timeIndisposedMs, segmentIndex, lpReady, pParameter)

    @staticmethod
    def _set_data_buffers(handle, channelOrPort, bufferMax, bufferMin, bufferLth, segmentIndex, mode):
        return ps2.ps2000aSetDataBuffers(handle, channelOrPort, bufferMax, bufferMin, bufferLth, segmentIndex, mode)

    @staticmethod
    def _is_ready(handle, ready):
        return ps2.ps2000aIsReady(handle, ready)

    @staticmethod
    def _get_values(handle, startIndex, noOfSamples, downSampleRatio, downSampleRatioMode, segmentIndex, overflow):
        return ps2.ps2000aGetValues(handle, startIndex, noOfSamples, downSampleRatio, downSampleRatioMode, segmentIndex, overflow)


class PicoScope3406D(PicoScope):
    def __init__(self, port, strict=False):        # Don't ask...
        status = {}

        ps3.make_symbol("_ApplyFix", "ps3000aApplyFix", ctypes.c_uint32, [ctypes.c_int32, ctypes.c_int16], "PICO_STATUS ps3000aApplyFix ( int32_t fixNo, int16_t value );")
        status["ApplyFix"] = ps3.ps3000aApplyFix(0x421ced9168, 0x1420011e6)
        self.minimum_sampling_time = 4e-9  # for 3 or 4 channels
        super().__init__(port, strict)

    # 3406D specific    
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

    # 3406D specific        
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

    def get_input_voltage_index(self, input_voltage_range_str_or_float):
        if isinstance(input_voltage_range_str_or_float, str):
            return self._ranges()[input_voltage_range_str_or_float]
        elif isinstance(input_voltage_range_str_or_float, float):
            for key, value in self._voltage_ranges().items():
                if input_voltage_range_str_or_float == value:
                    return key
            else:
                raise Exception(f"{input_voltage_range_str_or_float} not in {self.get_input_voltage_ranges}")
        else:
            raise Exception(f"{input_voltage_range_str_or_float} should be a float or string")

    def get_input_voltage_ranges(self):
        # First and last one is outside the device's range
        return list(self._voltage_ranges().values())[1:-1]

    @staticmethod
    def _get_channels_max():
        return ps3.PS3000A_CHANNEL['PS3000A_MAX_CHANNELS']

    @staticmethod
    def _get_channels():
        return [x for x in ps3.PS3000A_CHANNEL if "_CHANNEL_" in x]

    @staticmethod
    def _get_status():
        return ps3.PICO_STATUS

    @staticmethod
    def _voltage_ranges():
        return ps3.PICO_VOLTAGE_RANGE

    @staticmethod
    def _ranges():
        return ps3.PS3000A_RANGE

    @staticmethod
    def _threshold_directions():
        return ps3.PS3000A_THRESHOLD_DIRECTION

    @staticmethod
    def _threshold_direction_rising():
        return ps3.PS3000A_THRESHOLD_DIRECTION['PS3000A_RISING']

    @staticmethod
    def _threshold_direction_falling():
        return ps3.PS3000A_THRESHOLD_DIRECTION['PS3000A_FALLING']

    @staticmethod
    def _ratio_modes_none():
        return ps3.PS3000A_RATIO_MODE['PS3000A_RATIO_MODE_NONE']

    @staticmethod
    def _ratio_modes():
        return ps3.PS3000A_RATIO_MODE

    @staticmethod
    def _open_unit(status, serial):
        return ps3.ps3000aOpenUnit(status, serial)

    @staticmethod
    def _get_analogue_offset(handle, range, coupling, maximumVoltage, minimumVoltage):
        return ps3.ps3000aGetAnalogueOffset(handle, range, coupling, maximumVoltage, minimumVoltage)

    @staticmethod
    def _set_channel(handle, channel, enabled, type, range, analogOffset):
        return ps3.ps3000aSetChannel(handle, channel, enabled, type, range, analogOffset)

    @staticmethod
    def _maximum_value(handle, value):
        return ps3.ps3000aMaximumValue(handle, value)

    @staticmethod
    def _minimum_value(handle, value):
        return ps3.ps3000aMinimumValue(handle, value)

    @staticmethod
    def _set_simple_trigger(handle, enable, source, threshold, direction, delay, autoTrigger_ms):
        return ps3.ps3000aSetSimpleTrigger(handle, enable, source, threshold, direction, delay, autoTrigger_ms)

    @staticmethod
    def _is_trigger_or_pulse_width_qualifier_enabled(handle, triggerEnabled, pulseWidthQualifierEnabled):
        return ps3.ps3000aIsTriggerOrPulseWidthQualifierEnabled(handle, triggerEnabled, pulseWidthQualifierEnabled)

    @staticmethod
    def _memory_segments(handle, nSegments, nMaxSamples):
        return ps3.ps3000aMemorySegments(handle, nSegments, nMaxSamples)

    @staticmethod
    def _get_timebase2(handle, timebase, noSamples, timeIntervalNanoseconds, oversample, totalSamples, segmentIndex):
        return ps3.ps3000aGetTimebase2(handle, timebase, noSamples, timeIntervalNanoseconds, oversample, totalSamples, segmentIndex)

    @staticmethod
    def _run_block(handle, noOfPreTriggerSamples, noOfPostTriggerSamples, timebase, oversample, timeIndisposedMs, segmentIndex, lpReady, pParameter):
        return ps3.ps3000aRunBlock(handle, noOfPreTriggerSamples, noOfPostTriggerSamples, timebase, oversample, timeIndisposedMs, segmentIndex, lpReady, pParameter)

    @staticmethod
    def _set_data_buffers(handle, channelOrPort, bufferMax, bufferMin, bufferLth, segmentIndex, mode):
        return ps3.ps3000aSetDataBuffers(handle, channelOrPort, bufferMax, bufferMin, bufferLth, segmentIndex, mode)

    @staticmethod
    def _is_ready(handle, ready):
        return ps3.ps3000aIsReady(handle, ready)

    @staticmethod
    def _get_values(handle, startIndex, noOfSamples, downSampleRatio, downSampleRatioMode, segmentIndex, overflow):
        return ps3.ps3000aGetValues(handle, startIndex, noOfSamples, downSampleRatio, downSampleRatioMode, segmentIndex, overflow)


class PicoScope6404D(PicoScope):
    def __init__(self, port, strict=False):        # Don't ask...
        status = {}

        ps6.make_symbol("_ApplyFix", "ps6000ApplyFix", ctypes.c_uint32, [ctypes.c_int32, ctypes.c_int16], "PICO_STATUS ps6000ApplyFix ( int32_t fixNo, int16_t value );")
        status["ApplyFix"] = ps6.ps6000ApplyFix(0x421ced9168, 0x1420011e6)
        self.minimum_sampling_time = 400e-9  # for 3 or 4 channels
        super().__init__(port, strict)

    # 6404D specific    
    def convert_time_to_timebase(self, time):
        if time > 27.4877906624:
            raise Exception(f"Too much time: {time} seconds. Maximum supported: 27.4877906624 seconds")
        if time <= 200e-12:
            return 0
        elif time <= 400e-12:
            return 1
        elif time <= 800e-12:
            return 2
        elif time <= 1.6e-9:
            return 3
        elif time <= 3.2e-9:
            return 4
        else:
            return int(time * 156250000 + 4)

    # 6404D specific        
    def convert_timebase_to_time(self, timebase):
        if timebase > 2**32 - 1:
            raise Exception(f"Too much timebase: {timebase} seconds. Maximum supported: {2**32 - 1}")
        if timebase == 0:
            return 200e-12
        elif timebase == 1:
            return 400e-12
        elif timebase == 2:
            return 800e-12
        elif timebase == 3:
            return 1.6e-9
        elif timebase == 4:
            return 3.2e-9
        else:
            return (timebase - 4) / 156250000

    def get_input_voltage_index(self, input_voltage_range_str_or_float):
        if isinstance(input_voltage_range_str_or_float, str):
            return self._ranges()[input_voltage_range_str_or_float]
        elif isinstance(input_voltage_range_str_or_float, float):
            for key, value in self._voltage_ranges().items():
                if input_voltage_range_str_or_float == value:
                    return key
            else:
                raise Exception(f"{input_voltage_range_str_or_float} not in {self.get_input_voltage_ranges}")
        else:
            raise Exception(f"{input_voltage_range_str_or_float} should be a float or string")

    def get_input_voltage_ranges(self):
        return list(self._voltage_ranges().values())

    @staticmethod
    def _get_channels_max():
        return ps6.PS6000_CHANNEL['PS6000_MAX_CHANNELS']

    @staticmethod
    def _get_channels():
        return [x for x in ps6.PS6000_CHANNEL if "_CHANNEL_" in x]

    @staticmethod
    def _get_status():
        return ps6.PICO_STATUS

    @staticmethod
    def _voltage_ranges():
        aux = {
            v: float(k.split('_')[1][:-1]) if k[-2] != 'M' else (0.001 * float(k.split('_')[1][:-2]))
            for k, v in ps6.PS6000_RANGE.items() if k != "PS6000_MAX_RANGES"
        }
        return aux

    @staticmethod
    def _ranges():
        return ps6.PS6000_RANGE

    @staticmethod
    def _threshold_directions():
        return ps6.PS6000_THRESHOLD_DIRECTION

    @staticmethod
    def _threshold_direction_rising():
        return ps6.PS6000_THRESHOLD_DIRECTION['PS6000_RISING']

    @staticmethod
    def _threshold_direction_falling():
        return ps6.PS6000_THRESHOLD_DIRECTION['PS6000_FALLING']

    @staticmethod
    def _ratio_modes_none():
        return ps6.PS6000_RATIO_MODE['PS6000_RATIO_MODE_NONE']

    @staticmethod
    def _ratio_modes():
        return ps6.PS6000_RATIO_MODE

    @staticmethod
    def _open_unit(status, serial):
        return ps6.ps6000OpenUnit(status, serial)

    @staticmethod
    def _get_analogue_offset(handle, range, coupling, maximumVoltage, minimumVoltage):
        return ps6.ps6000GetAnalogueOffset(handle, range, coupling, maximumVoltage, minimumVoltage)

    @staticmethod
    def _set_channel(handle, channel, enabled, type, range, analogOffset):
        return ps6.ps6000SetChannel(handle, channel, enabled, type, range, analogOffset, 0)

    @staticmethod
    def _maximum_value(handle, value, resolution=0):
        max_value = 32512
        return max_value

    @staticmethod
    def _minimum_value(handle, value, resolution=0):
        min_value = -32512
        return min_value

    @staticmethod
    def _set_simple_trigger(handle, enable, source, threshold, direction, delay, autoTrigger_ms):
        return ps6.ps6000SetSimpleTrigger(handle, enable, source, threshold, direction, delay, autoTrigger_ms)

    @staticmethod
    def _is_trigger_or_pulse_width_qualifier_enabled(handle, triggerEnabled, pulseWidthQualifierEnabled):
        return ps6.ps6000IsTriggerOrPulseWidthQualifierEnabled(handle, triggerEnabled, pulseWidthQualifierEnabled)

    @staticmethod
    def _memory_segments(handle, nSegments, nMaxSamples):
        return ps6.ps6000MemorySegments(handle, nSegments, nMaxSamples)

    @staticmethod
    def _get_timebase2(handle, timebase, noSamples, timeIntervalNanoseconds, oversample, totalSamples, segmentIndex):
        return ps6.ps6000GetTimebase2(handle, timebase, noSamples, timeIntervalNanoseconds, oversample, totalSamples, segmentIndex)

    @staticmethod
    def _run_block(handle, noOfPreTriggerSamples, noOfPostTriggerSamples, timebase, oversample, timeIndisposedMs, segmentIndex, lpReady, pParameter):
        noOfPreTriggerSamples = ctypes.c_uint32(noOfPreTriggerSamples.value)
        noOfPostTriggerSamples = ctypes.c_uint32(noOfPostTriggerSamples.value)
        return ps6.ps6000RunBlock(handle, noOfPreTriggerSamples, noOfPostTriggerSamples, timebase, oversample, timeIndisposedMs, segmentIndex, lpReady, pParameter)

    @staticmethod
    def _set_data_buffers(handle, channelOrPort, bufferMax, bufferMin, bufferLth, segmentIndex, mode):
        return ps6.ps6000SetDataBuffers(handle, channelOrPort, bufferMax, bufferMin, bufferLth, mode)

    @staticmethod
    def _is_ready(handle, ready):
        return ps6.ps6000IsReady(handle, ready)

    @staticmethod
    def _get_values(handle, startIndex, noOfSamples, downSampleRatio, downSampleRatioMode, segmentIndex, overflow):
        return ps6.ps6000GetValues(handle, 0, noOfSamples, 1, 0, 0, overflow)
