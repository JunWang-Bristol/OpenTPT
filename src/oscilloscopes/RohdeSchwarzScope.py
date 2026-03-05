import warnings
import pyvisa
import numpy
import pandas
from oscilloscope import Oscilloscope

# Some instruments (including the RTB2004 over VXI-11) return responses that end
# with '\n' only, not '\r\n'.  PyVISA emits a UserWarning when the received string
# doesn't match read_termination exactly.  Suppress that specific warning so it
# doesn't clutter the console output during normal operation.
warnings.filterwarnings(
    "ignore",
    message="read string doesn't end with termination characters",
    category=UserWarning,
    module="pyvisa",
)

# ----------------- RTB2004 Scope -----------------

class RTB2004Scope(Oscilloscope):
    """
    Rohde & Schwarz RTB2004 oscilloscope driver using SCPI over VISA.

    Usage example
    -------------
    scope = RTB2004Scope("TCPIP0::192.168.0.50::INSTR")
    scope.set_number_samples(10000)
    scope.set_sampling_time(1e-6)  # 1 us/sample -> ~10 ms record
    scope.set_channel_configuration("A", 0.1, "DC", 0.0)
    scope.set_rising_trigger("A", 0.5)
    scope.run_acquisition_block()
    df = scope.read_data(["A"])
    """

    class ChannelInfo:
        def __init__(self, index, input_voltage_range, coupling, analog_offset):
            self.index = index
            self.enabled = True
            # For RTB we treat input_voltage_range as vertical SCALE (V/div)
            self.input_voltage_range = input_voltage_range
            self.coupling = coupling
            self.analog_offset = analog_offset

        def enable(self):
            self.enabled = True

        def disable(self):
            self.enabled = False

    class TriggerInfo:
        def __init__(self, index, threshold_voltage, direction, delayed_samples, timeout):
            self.index = index
            self.enabled = True
            self.threshold_voltage = threshold_voltage
            # "RISING" / "FALLING"
            self.direction = direction
            self.delayed_samples = delayed_samples
            self.timeout = timeout

        def enable(self):
            self.enabled = True

        def disable(self):
            self.enabled = False

    def __init__(self, resource, strict=False, visa_library=None):
        """
        Parameters
        ----------
        resource : str
            VISA resource string, e.g. "TCPIP0::192.168.0.50::INSTR" or USB resource.
        strict : bool
            If True, enforce input voltage ranges exactly (not heavily used here).
        visa_library : str | None
            Optional path to a specific VISA library; if None, use default.
        """
        self.strict = strict

        # Open VISA session
        #rm = pyvisa.ResourceManager(visa_library) if visa_library else pyvisa.ResourceManager()
        #self.inst = rm.open_resource(resource)
        #self.inst.timeout = 10000  # ms, can be tuned

        rm = pyvisa.ResourceManager()

        try:
            self.inst = rm.open_resource(resource)
            self.inst.timeout = 1000
            self.inst.read_termination = '\n'
            self.inst.write_termination = '\n'
            # try sending query
            idn = self.inst.query('*IDN?')
            print(f'Connected to: {idn.strip()}')
        except Exception as e:
            print('Warning: oscilloscope offline.', e)
            # messagebox to indicate error
            #messagebox.showerror('Error', 'The RTB2004 is offline. Check power and connections. Then close and restart.')
        else:
            self.inst.timeout = 5000
            self.inst.write('*CLS')
            # Initialize trigger to AUTO mode (disarmed)
            self.inst.write('TRIGger:A:MODE AUTO')


        # Basic identification (optional, but handy for debugging)
        #try:
        #    idn = self.inst.query("*IDN?")
        #    print(f"Connected to: {idn.strip()}")
        #except Exception as exc:
        #    print(f"Warning: *IDN? failed: {exc}")

        # Generic state similar to PicoScope base
        self.channel_info = {}
        self.trigger_info = {}
        self.number_segments = 1  # RTB has segmented memory, but we treat as 1 segment here
        self.number_samples = 10000  # default; can be changed via set_number_samples()
        self.sampling_time = 1e-6    # default 1 µs/sample
        self.number_pre_trigger_samples = 0
        self.upsampling_scale = 1
        self.upsampled_sampling_time = self.sampling_time

        self.probe_scale = {}
        self.channel_labels = {}
        self.channel_skew = {}

        # Initialize 4 analog channels A..D mapped to CHAN1..CHAN4
        for ch in ["A", "B", "C", "D"]:
            ch_idx = self.check_channel(ch)
            self.channel_labels[ch_idx] = ch
            self.channel_skew[ch_idx] = 0.0

        # Reasonable defaults for export path/base name; adjust as needed
        # This is the file *base* name without extension used for EXPort:WAVeform:NAME
        self.waveform_base_path = "/INT/Temp/RTB_TMP"

    # ----------------- Basic configuration -----------------

    def close(self):
        """Close VISA session."""
        try:
            self.inst.close()
        except Exception:
            pass

    def set_number_pre_trigger_samples(self, number_pre_trigger_samples):
        self.number_pre_trigger_samples = int(number_pre_trigger_samples)

    def get_number_pre_trigger_samples(self):
        return self.number_pre_trigger_samples

    def get_number_upsampled_pre_trigger_samples(self):
        return self.number_pre_trigger_samples * self.upsampling_scale

    def set_number_samples(self, number_samples):
        self.number_samples = int(number_samples)

    def get_number_samples(self):
        return self.number_samples

    def get_upsampling_scale(self):
        return self.upsampling_scale

    def get_upsampled_sampling_time(self):
        return self.upsampled_sampling_time

    def set_sampling_time(self, desired_sampling_time):
        """
        For RTB we simply store the desired sampling time and use it to set
        the acquisition time in run_acquisition_block.
        """
        self.sampling_time = float(desired_sampling_time)
        self.upsampled_sampling_time = self.sampling_time
        return self.sampling_time

    def get_sampling_time(self):
        return self.sampling_time

    def set_channel_skew(self, channel, skew):
        ch_idx = self.check_channel(channel)
        self.channel_skew[ch_idx] = float(skew)

    def get_channel_skew(self, channel):
        ch_idx = self.check_channel(channel)
        return self.channel_skew[ch_idx]
    
    def getAnalogueOffset(self, channel: int, vrange: float, coupling: str):
        """
        PicoScope-compatible wrapper:
        
        Equivalent to:
            ps6000GetAnalogueOffset(handle, range, coupling, maximumVoltage, minimumVoltage)

        For the RTB2004:
        - 'vrange' maps to vertical scale in V/div (you can adjust if you want full-scale)
        - 'coupling' must be 'AC' or 'DC'
        
        Returns:
            (maximumVoltage, minimumVoltage)
        """

        ch = f":CHANnel{channel}"

        # Set coupling (PicoScope uses integer enums but RTB uses SCPI strings)
        coupling = coupling.upper()
        if coupling not in ("AC", "DC"):
            raise ValueError("Coupling must be 'AC' or 'DC'")
        self.inst.write(f"{ch}:COUPling {coupling}")

        # Set the vertical scale for RTB2004
        # NOTE: PicoScope 'range' is full-scale; RTB uses V/div. 
        # If your code uses full-scale, divide by 10 here.
        scale = vrange   # (adjust if your vrange is full-scale!)

        # Probe the scope for allowed offset range
        min_off, max_off = self.get_allowed_offset_range(channel, scale)

        # PicoScope returns (max, min)
        return max_off, min_off

    
    @staticmethod
    def _get_analogue_offset(handle, range, coupling, maximumVoltage, minimumVoltage):
        #return ps6.ps6000GetAnalogueOffset(handle, range, coupling, maximumVoltage, minimumVoltage)
        return self.getAnalogueOffset(channel, vrange, coupling)
    


    # ----------------- Channel helpers -----------------

    def get_number_channels(self):
        return 4  # RTB2004 = 4 analog channels

    def get_channel_index(self, channel_name):
        """
        Accepts names like "A", "B", "C", "D" or "1".."4".
        Returns zero-based index 0..3.
        """
        return self.check_channel(channel_name)

    def set_channel_label(self, channel, label):
        ch_idx = self.check_channel(channel)
        self.channel_labels[ch_idx] = label

    def set_probe_scale(self, channel, probe_scale):
        ch_idx = self.check_channel(channel)
        self.probe_scale[ch_idx] = float(probe_scale)
        # scale example is 10 for 10x probe, 1 for direct BNc
        self.inst.write(f"PROBE{ch_idx}:SETUP:ATTENUATION:MANUAL {probe_scale}")

    def get_probe_scale(self, channel):
        ch_idx = self.check_channel(channel)

        return self.probe_scale.get(ch_idx, 1.0)
    
    def set_probe_units(self, channel, units):
        # units are V or A
        ch_idx = self.check_channel(channel)
        self.inst.write(f"PROBE{ch_idx}:SETUP:ATTENUATION:UNITS {units}")

    def check_channel(self, channel):
        """
        Map user-friendly names to 0-based indices 0..3.
        Returns 0-based index for internal use; hardware commands need +1.
        Accepts only 0-based (0-3)
        """
        if isinstance(channel, str):
            if "_CHANNEL_" in channel:
                channel = channel.split("_CHANNEL_")[1]

            # Allow numeric strings "0".."3"
            if channel in ["0", "1", "2", "3"]:
                return int(channel+1)
            # Letter names map to 1-based indices
            # should not be needed
            if channel.upper() == "A":
                return 1
            if channel.upper() == "B":
                return 2
            if channel.upper() == "C":
                return 3
            if channel.upper() == "D":
                return 4
            raise Exception(f"Channel {channel} does not exist on RTB2004")
        elif isinstance(channel, (int, float)):
            ch = int(channel)
            # Accept both 0-based (0-3) and 1-based (1-4) indexing
            # Priority: treat 0-3 as 0-based first, then 4 as 1-based
            if ch >= 0 and ch < self.get_number_channels():
                return ch+1  # Already 0-based (0-3) to 1-4 based
            #elif ch == self.get_number_channels():
            #    return ch - 1  # Channel 4 -> index 3 (1-based to 0-based)
            else:
                raise Exception(f"Channel {channel} does not exist on RTB2004")
        else:
            raise Exception(f"Channel {channel} does not exist on RTB2004")

    # ----------------- Vertical / channel configuration -----------------

    def get_input_voltage_ranges(self):
        """
        RTB2000 vertical scales: 1 mV/div .. 5 V/div (depending on probe).
        We expose some typical scales here as 'allowed' values (in V/div).
        """
        # vertical scales [1e-3, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]
        # range will be 10x becuase there are 10 divisions vertically
        return [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100]

    def check_input_voltage_range(self, input_voltage_range):
        """
        For RTB we interpret 'input_voltage_range' as V/div.
        If strict=False we pick the next higher available scale.
        """
        if isinstance(input_voltage_range, (int, float)):
            val = float(input_voltage_range)
        else:
            raise Exception(f"Input voltage range {input_voltage_range} should be a float in V/div")

        allowed = self.get_input_voltage_ranges()
        if val in allowed or self.strict:
            return val

        for r in allowed:
            if r >= val:
                return r
        return allowed[-1]
    
    def get_analog_offset_range(self, coupling, input_voltage_range):
        """
        Compute allowable DC offset range for an RTB2004 channel, in volts at the BNC.
        volts_per_div_bnc: vertical scale at the *BNC* in V/div
        position_div: vertical position in divisions (-5 to +5), 0 = center

        Returns (min_offset, max_offset) in volts.
        """
        """
        volts_per_div_bnc = float(input_voltage_range/10.0)  # V/div at BNC (10 div vertical)

        S = volts_per_div_bnc
        P = 0  # center position (we don't expose position adjustment here)

        if S < 0.001 or S > 5.0:
            raise ValueError("Input sensitivity must be between 1 mV/div and 5 V/div (at BNC).")

        if S >= 0.2:
            max_abs_offset = 40.0 - P * S  # 200 mV/div to 5 V/div
        else:
            max_abs_offset = 1.2 - P * S   # 1 mV/div to < 200 mV/div

        if max_abs_offset < 0:
            # No valid offset for that combo of position & sensitivity
            return 0.0, 0.0

        return [-max_abs_offset, max_abs_offset]
        """
    
        scale = float(self.inst.query(":CHAN1:SCAL?"))
        probe = float(self.inst.query("PROBe1:SETup:ATTenuation:Manual?"))
        max_off = self.rtb2004_max_offset(scale, probe)
        print("Max offset allowed:", max_off, "V")

        return (-max_off, max_off)

    
    def rtb2004_max_offset(self, scale, probe=1):
        # Analog input range limits from RTB2004 specs (in Volts)
        limits = [
            (0.05, 0.5),
            (0.1, 1.0),
            (0.2, 2.0),
            (0.5, 5.0),
            (1.0, 10.0),
            (5.0, 20.0),
            (10.0, 50.0),
        ]

        # find matching limit
        max_range = None
        for s, r in limits:
            if scale <= s:
                max_range = r
                break

        if max_range is None:
            return None  # unsupported range

        # apply probe attenuation
        max_range *= probe

        # compute max offset
        return max_range - 5 * scale * probe



    def set_channel_configuration(self, channel, input_voltage_range, coupling, analog_offset, enable=True):
        """
        Map to:
          CHANnel<m>:STATe ON/OFF
          CHANnel<m>:SCALe <scale>
          CHANnel<m>:OFFSet <offset>
          CHANnel<m>:COUPling <coupling>
        """
        ch_idx = self.check_channel(channel)
        hw_ch = ch_idx

        scale = self.check_input_voltage_range(input_voltage_range)

        # Normalize coupling string if given
        coup = str(coupling).upper()
        if coup.startswith("DC") or coup == "0":
            coup = "DC"
        elif coup.startswith("AC") or coup == "1":
            coup = "AC"
        elif coup.startswith("GND"):
            coup = "GND"

        # Apply to instrument
        self.inst.write(f"CHANnel{hw_ch}:SCALe {scale}")
        self.inst.write(f"CHANnel{hw_ch}:OFFSet {analog_offset}")
        self.inst.write(f"CHANnel{hw_ch}:COUPling {coup}")
        self.inst.write(f"CHANnel{hw_ch}:STATe {'ON' if enable else 'OFF'}")

        self.channel_info[ch_idx] = self.ChannelInfo(ch_idx, scale, coup, analog_offset)
        self.channel_labels[ch_idx] = channel  # keep whatever user passed as label
        return True

    def get_channel_configuration(self, channel):
        ch_idx = self.check_channel(channel)
        if ch_idx not in self.channel_info:
            raise Exception(f"Channel {ch_idx} has not been configured yet")
        return self.channel_info[ch_idx]

    def enable_channel(self, channel):
        ch_idx = self.check_channel(channel)
        hw_ch = ch_idx
        self.inst.write(f"CHANnel{hw_ch}:STATe ON")
        if ch_idx not in self.channel_info:
            # Keep a minimal record
            self.channel_info[ch_idx] = self.ChannelInfo(ch_idx, 0.1, "DC", 0.0)

    def disable_channel(self, channel):
        ch_idx = self.check_channel(channel)
        hw_ch = ch_idx
        self.inst.write(f"CHANnel{hw_ch}:STATe OFF")
        if ch_idx in self.channel_info:
            self.channel_info[ch_idx].enabled = False

    # ----------------- Trigger configuration -----------------

    def set_trigger(self, channel, threshold_voltage, direction, delayed_samples=0, timeout=0, enable=True):
        """
        direction: "RISING" or "FALLING" (case-insensitive).
        Maps to TRIGger:A:EDGE subsystem.
        """
        ch_idx = self.check_channel(channel)
        hw_ch = ch_idx 

        dir_upper = str(direction).upper()
        if "RISING" in dir_upper or "POS" in dir_upper:
            slope = "POS"
        elif "FALLING" in dir_upper or "NEG" in dir_upper:
            slope = "NEG"
        else:
            slope = "POS"

        if enable:
            self.inst.write("TRIGger:A:MODE NORMal")
            self.inst.write("TRIGger:A:TYPE EDGE")
            self.inst.write(f"TRIGger:A:EDGE:SOURce CHAN{hw_ch}")
            self.inst.write(f"TRIGger:A:EDGE:SLOPe {slope}")
            self.inst.write(f"TRIGger:A:LEVel1 {threshold_voltage}")
        else:
            # Simplest 'disarm' is to put trigger into AUTO mode
            self.inst.write("TRIGger:A:MODE AUTO")

        # Convert slope to integer direction code (2=rising, 3=falling) for compatibility
        direction_code = 2 if slope == "POS" else 3
        self.trigger_info[ch_idx] = self.TriggerInfo(
            ch_idx, float(threshold_voltage), direction_code, delayed_samples, timeout
        )

    def set_rising_trigger(self, channel, threshold_voltage, delayed_samples=0, timeout=0):
        self.set_trigger(channel, threshold_voltage, "RISING", delayed_samples, timeout, True)

    def set_falling_trigger(self, channel, threshold_voltage, delayed_samples=0, timeout=0):
        self.set_trigger(channel, threshold_voltage, "FALLING", delayed_samples, timeout, True)

    def get_trigger_configuration(self, channel):
        ch_idx = self.check_channel(channel)
        if ch_idx not in self.trigger_info:
            raise Exception(f"Trigger for channel {ch_idx} has not been configured yet")
        return self.trigger_info[ch_idx]

    def arm_trigger(self, channel):
        ch_idx = self.check_channel(channel)
        info = self.trigger_info[ch_idx]
        # Convert direction code (2=rising, 3=falling) back to string
        direction_str = "RISING" if info.direction == 2 else "FALLING"
        self.set_trigger(ch_idx, info.threshold_voltage, direction_str, info.delayed_samples, info.timeout, True)

    def disarm_trigger(self, channel):
        ch_idx = self.check_channel(channel)
        info = self.trigger_info[ch_idx]
        # Convert direction code (2=rising, 3=falling) back to string
        direction_str = "RISING" if info.direction == 2 else "FALLING"
        self.set_trigger(ch_idx, info.threshold_voltage, direction_str, info.delayed_samples, info.timeout, False)

    def is_trigger_armed(self):
        # Check if trigger mode is NORMAL (armed) vs AUTO (disarmed)
        try:
            mode1 = self.inst.query("ACQuire:STATe?").strip().upper()
            if mode1 == 'COMP' or mode1 == 'STOP' or mode1 == 'BRE':
                return False
            else:
                return True
            #return mode1 == "RUN"
            #mode = self.inst.query("TRIGger:A:MODE?").strip().upper()
            #return mode == "NORM" or mode == "NORMAL"
        except Exception:
            return False

    # ----------------- Acquisition / timebase -----------------

    def get_maximum_samples(self):
        """
        Query the actual record length from the scope.
        RTB2004 has up to 10 Mpoints per channel standard, 20 Mpoints interleaved.
        """
        try:
            record_length = int(self.inst.query("ACQuire:POINts?"))
            return record_length
        except Exception:
            # Fallback to theoretical maximum
            return 10_000_000

    def convert_time_to_timebase(self, time):
        """
        Pico-specific timebase concept doesn't apply here; we just return the time itself.
        """
        return float(time)

    def convert_timebase_to_time(self, timebase):
        return float(timebase)

    def get_real_sampling_time(self, desired_time=None, desired_number_samples=None):
        """
        For RTB, the 'real' sampling time will be whatever the scope picks for the
        requested acquisition time / memory depth. Here we simply return the internally
        stored sampling_time.
        """
        if desired_number_samples is not None:
            self.number_samples = int(desired_number_samples)
        if desired_time is not None:
            self.sampling_time = float(desired_time)
        return self.sampling_time

    def run_acquisition_block(self, sampling_time=None, number_samples=None):
        """
        Configure acquisition time and run a single-shot acquisition.

        Maps to:
          ACQuire:STOPAfter SEQuence
          ACQuire:NSINgle:COUNt 1
          TIMebase:ACQTime <T>
          RUNSingle; *OPC?
        """
        if number_samples is None:
            number_samples = self.number_samples
        if sampling_time is None:
            sampling_time = self.sampling_time

        self.number_samples = int(number_samples)
        self.sampling_time = float(sampling_time)

        acquisition_time = self.number_samples * self.sampling_time

        # Set acquisition time (total time span)
        self.inst.write(f"TIMebase:ACQTime {acquisition_time}")
        # Single-shot, 1 acquisition
        self.inst.write("ACQuire:STOPAfter SEQuence")
        self.inst.write("ACQuire:NSINgle:COUNt 1")

        # Start single acquisition and wait for completion
        self.inst.write("RUNSingle")
        # Synchronize: *OPC? blocks until acquisition complete
        #_ = self.inst.query("*OPC?")

        return True

    def set_acquisition_time(self, acq_time_s):
        """Set the total acquisition window [s]. RTB2004: TIMebase:ACQTime."""
        self.inst.write(f"TIMebase:ACQTime {acq_time_s}")

    def start_single_acquisition(self):
        """Arm and start a single-shot acquisition. RTB2004: RUNSingle."""
        self.inst.write("RUNSingle")

    def get_acquisition_state(self):
        """Return the current acquisition state string ('COMP', 'RUN', 'STOP', ...)."""
        return self.inst.query("ACQuire:STATe?").strip().upper()

    def set_read_timeout(self, timeout_ms):
        """Temporarily extend the VISA read timeout for slow data transfers."""
        self._saved_timeout = self.inst.timeout
        self.inst.timeout = int(timeout_ms)

    def reset_read_timeout(self):
        """Restore the VISA read timeout saved by set_read_timeout()."""
        self.inst.timeout = self._saved_timeout

    # ----------------- Data readout -----------------

    def _export_waveform_csv(self, channel, filename_base):
        """
        Export one channel to CSV on the scope's file system using EXPort:WAVeform.
        """
        ch_idx = self.check_channel(channel)
        hw_ch = ch_idx

        # Select CSV as export format
        self.inst.write("FORMat:DATA CSV") #ok
        # Choose waveform source
        self.inst.write(f"EXPort:WAVeform:SOURce CH{hw_ch}") #was chan, now ok
        # Set path + base name (no extension) for export
        self.inst.write(f'EXPort:WAVeform:NAME "{filename_base}"') #ok
        # Execute export
        self.inst.write("EXPort:WAVeform:SAVE") #ok
        # Wait for export to complete
        _ = self.inst.query("*OPC?")

    def _read_exported_csv(self, filename_base):
        """
        Read CSV file content back over SCPI using MMEM:DATA?.

        NOTE: Path / extension may need adjustment depending on firmware:
        often you need something like:
            MMEM:DATA? \"/INT/Temp/RTB_TMP.CSV\"
        """
        # Most firmwares append .CSV to the given base name when FORMAT CSV is selected
        path_with_ext = f"{filename_base}.CSV"
        self.inst.write(f'MMEM:DATA? "{path_with_ext}"')
        raw = self.inst.read_raw()
        # Strip the SCPI binary block header if present, then decode
        # Very simple parser: if it starts with '#', treat as block
        if raw.startswith(b"#"):
            # '#', one digit n, then n digits length, then data
            n_digits = int(raw[1:2].decode("ascii"))
            length = int(raw[2:2 + n_digits].decode("ascii"))
            data = raw[2 + n_digits:2 + n_digits + length]
        else:
            data = raw
        text = data.decode("utf-8", errors="ignore")
        return text

    def read_data(self, channels=None, number_samples=None, data_format="dataframe"):
        """
        Acquire waveform data into a pandas DataFrame using CHANnel<n>:DATA? command.

        This directly queries waveform data from the scope's acquisition memory.
        """
        if number_samples is not None:
            self.number_samples = int(number_samples)

        if channels is None:
            channels = list(self.channel_info.keys())
        # Normalize channel list to indices
        ch_indices = [self.check_channel(ch) for ch in channels]

        all_data = {}
        common_time = None

        for ch_idx in ch_indices:
            label = self.channel_labels.get(ch_idx, f"CHAN{ch_idx}")
            hw_ch = ch_idx

            # Set format to ASCII for easier parsing
            self.inst.write("FORMat:DATA ASCII")

            # Query waveform data for this channel
            try:
                # Get the waveform data
                waveform_data = self.inst.query(f"CHANnel{hw_ch}:DATA?")

                # Parse the comma-separated values
                values = []
                for val_str in waveform_data.split(","):
                    try:
                        values.append(float(val_str.strip()))
                    except ValueError:
                        continue

                arr_v = numpy.array(values)

                # Get timebase information to construct time array
                if common_time is None:
                    # Use scope's reported scale and position for the time axis.
                    time_scale    = float(self.inst.query("TIMebase:SCALe?"))
                    time_position = float(self.inst.query("TIMebase:POSition?"))
                    record_length = int(self.inst.query("ACQuire:POINts?"))
                    total_time    = time_scale * 10   # 10 divisions
                    dt            = total_time / record_length
                    common_time = numpy.arange(len(arr_v)) * dt - time_position

                # Verify all channels have the same length
                if common_time is not None and len(arr_v) != len(common_time):
                    print(f"WARNING: Channel {hw_ch} has {len(arr_v)} samples but time array has {len(common_time)} samples")
                    # Truncate or pad to match
                    if len(arr_v) > len(common_time):
                        arr_v = arr_v[:len(common_time)]
                    else:
                        # Pad with last value
                        arr_v = numpy.pad(arr_v, (0, len(common_time) - len(arr_v)), mode='edge')

                # Assume time base identical between channels
                all_data[label] = arr_v

            except Exception as e:
                print(f"ERROR reading channel {hw_ch}: {e}")
                import traceback
                traceback.print_exc()
                # Return empty array for this channel
                all_data[label] = numpy.array([])

        if common_time is None:
            common_time = numpy.array([])

        # Ensure all data arrays have the same length as common_time
        if len(common_time) > 0:
            for label, vals in all_data.items():
                if len(vals) != len(common_time):
                    print(f"WARNING: Adjusting {label} from {len(vals)} to {len(common_time)} samples")
                    if len(vals) > len(common_time):
                        all_data[label] = vals[:len(common_time)]
                    elif len(vals) < len(common_time):
                        all_data[label] = numpy.pad(vals, (0, len(common_time) - len(vals)), mode='edge')

        if data_format == "dataframe":
            df = pandas.DataFrame()
            df["time"] = common_time
            for label, vals in all_data.items():
                df[label] = vals

            if not isinstance(df.index, pandas.RangeIndex) or not df.index.is_monotonic_increasing:
                df = df.reset_index(drop=True)
            return df

        # Else return dict(time=array, data={label: array})
        return {"time": common_time, "data": all_data}
