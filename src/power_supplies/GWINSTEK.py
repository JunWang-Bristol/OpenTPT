import warnings
import pyvisa

from power_supply import PowerSupply

# Suppress the PyVISA UserWarning that fires when an instrument response doesn't
# end with the configured read_termination characters.  The GPP-4323 returns
# responses terminated with '\n' only; setting read_termination='\n' below
# handles most cases, but this filter catches any remaining edge cases.
warnings.filterwarnings(
    "ignore",
    message="read string doesn't end with termination characters",
    category=UserWarning,
    module="pyvisa",
)

class GPP4323(PowerSupply):
    """
    Driver for GW Instek GPP-4323 programmable DC power supply.

    This class mirrors the public API of the BK class in this module,
    but uses the SCPI commands defined for the GPP-4323 series.
    """

    def __init__(self, port):
        rm = pyvisa.ResourceManager()
        # Allow being passed "COM3" or just "3" etc., like BK
        if "COM" in port.upper():
            # split on "COM" and take the numeric part
            port = port.upper().split("COM")[1]

        try:
            self.visa_session = rm.open_resource(port)
            self.visa_session.timeout = 1000
            self.visa_session.read_termination = '\n'
            self.visa_session.write_termination = '\n'
            # try sending query
            idn = self.visa_session.query('*IDN?')
            print(f'Connected to {idn.strip()}')
        except Exception as e:
            print('Warning: power supply offline.', e)
            # messagebox to indicate error
            #messagebox.showerror('Error', 'The GPP4323 is offline. Check power and connections. Then close and restart.')
        else:
            print('GPP4323 online')
            self.visa_session.timeout = 5000
            self.visa_session.write('*CLS')

        # Use the same ASRL scheme as the BK supply (RS-232)
        #self.visa_session = rm.open_resource(port)

        #self.visa_session.timeout = 10000  # milliseconds
        #self.visa_session.read_termination = "\n"

        # Put device into remote control mode
        # (:SYSTem:REMote is the documented remote-mode command)
        #self.visa_session.write(":SYSTem:REMote")
        #self.visa_session.write("*WAI")

        # Basic sanity check that we really have a GPP-4323
        idn = self.visa_session.query("*IDN?").strip()
        assert "GPP-4323" in idn, f"Unexpected IDN string for GPP-4323: {idn}"

        self.voltages = None
        # GPP-4323 has 4 channels
        self.channels = [1, 2, 3, 4]

        # Local mirrors for series/parallel state (no simple query)
        self._series_enabled = False
        self._parallel_enabled = False

    # ------------------------------------------------------------------
    # Basic instrument info / setup
    # ------------------------------------------------------------------
    def reset(self):
        self.visa_session.write("*RST")

    def get_version(self):
        # GPP series uses :SYSTem:VERSion?
        return self.visa_session.query(":SYSTem:VERSion?")

    def get_available_channels(self):
        return self.channels

    def check_channel(self, channel):
        if isinstance(channel, str):
            try:
                channel = int(channel)
            except ValueError:
                raise AssertionError(f"Wrong channel index: {channel}")
        assert channel in self.channels, f"Wrong channel index: {channel}"

    # ------------------------------------------------------------------
    # Output enable / disable
    # ------------------------------------------------------------------
    def enable_output(self, channel):
        self.check_channel(channel)
        # Channel-specific output control
        self.visa_session.write(f":OUTPut{int(channel)}:STATe ON")
        #self.visa_session.write("*WAI")
        _ = self.visa_session.query("*OPC?").strip()
        state = self.visa_session.query(f":OUTPut{int(channel)}:STATe?").strip().upper()
        return state in ("1", "ON")

    def is_output_enabled(self, channel):
        self.check_channel(channel)
        state = self.visa_session.query(f":OUTPut{int(channel)}:STATe?").strip().upper()
        return state in ("1", "ON")

    def enable_all_outputs(self):
        # ALLOUTON turns on all channels
        self.visa_session.write("ALLOUTON")
        #self.visa_session.write("*WAI")
        _ = self.visa_session.query("*OPC?").strip()
        # Verify at least CH1 is on
        state = self.visa_session.query(":OUTPut1:STATe?").strip().upper()
        return state in ("1", "ON")

    def disable_output(self, channel):
        self.check_channel(channel)
        self.visa_session.write(f":OUTPut{int(channel)}:STATe OFF")
        #self.visa_session.write("*WAI")
        _ = self.visa_session.query("*OPC?").strip()
        state = self.visa_session.query(f":OUTPut{int(channel)}:STATe?").strip().upper()
        return state in ("0", "OFF")

    def disable_all_outputs(self):
        self.visa_session.write("ALLOUTOFF")
        #self.visa_session.write("*WAI")
        _ = self.visa_session.query("*OPC?").strip()
        state = self.visa_session.query(":OUTPut1:STATe?").strip().upper()
        return state in ("0", "OFF")

    # ------------------------------------------------------------------
    # Series / parallel tracking
    # ------------------------------------------------------------------
    def is_series_mode_enabled(self):
        # No explicit :OUTPut:SERies? query documented,
        # so we just reflect the last command we sent.
        return self._series_enabled

    def enable_series_mode(self):
        self.visa_session.write(":OUTPut:SERies ON")
        #self.visa_session.write("*WAI")
        _ = self.visa_session.query("*OPC?").strip()
        self._series_enabled = True
        return True

    def disable_series_mode(self):
        self.visa_session.write(":OUTPut:SERies OFF")
        #self.visa_session.write("*WAI")
        _ = self.visa_session.query("*OPC?").strip()
        self._series_enabled = False
        return True

    def is_parallel_mode_enabled(self):
        return self._parallel_enabled

    def enable_parallel_mode(self):
        self.visa_session.write(":OUTPut:PARallel ON")
        #self.visa_session.write("*WAI")
        _ = self.visa_session.query("*OPC?").strip()
        self._parallel_enabled = True
        return True

    def disable_parallel_mode(self):
        self.visa_session.write(":OUTPut:PARallel OFF")
        #self.visa_session.write("*WAI")
        _ = self.visa_session.query("*OPC?").strip()
        self._parallel_enabled = False
        return True

    # ------------------------------------------------------------------
    # Source settings (voltages / currents)
    # ------------------------------------------------------------------
    def set_all_source_voltages(self, voltages):
        assert len(voltages) >= len(self.channels), "Not enough voltage values"
        self.voltages = list(voltages)

        # GPP does not have a single "APP:VOLT" style command.
        # Set each channel individually, then wait for completion.
        for ch, v in zip(self.channels, self.voltages):
            self.visa_session.write(f":SOURce{ch}:VOLTage {v}")
            #self.visa_session.write("*WAI")

        return self.visa_session.query("*OPC?").strip() == "1"

    def set_source_voltage(self, channel, voltage):
        self.check_channel(channel)
        if self.voltages is None:
            self.voltages = [0.0] * len(self.channels)
        self.voltages[int(channel) - 1] = voltage
        self.visa_session.write(f":SOURce{int(channel)}:VOLTage {voltage}")
        #self.visa_session.write("*WAI")
        return self.visa_session.query("*OPC?").strip() == "1"

    def get_all_source_voltages(self):
        # Query all channel set voltages at once
        voltages_str = self.visa_session.query(":SOURce:VOLTage:ALL?")
        voltages = [float(x) for x in voltages_str.split(",")]
        return voltages

    def get_source_voltage(self, channel):
        self.check_channel(channel)
        v = float(self.visa_session.query(f":SOURce{int(channel)}:VOLTage?"))
        return v

    def set_current_limit(self, channel, limit):
        self.check_channel(channel)
        self.visa_session.write(f":SOURce{int(channel)}:CURRent {limit}")
        #self.visa_session.write("*WAI")
        return self.visa_session.query("*OPC?").strip() == "1"

    def get_current_limit(self, channel):
        self.check_channel(channel)
        limit = float(self.visa_session.query(f":SOURce{int(channel)}:CURRent?"))
        return limit

    def get_maximum_source_current(self, channel=1):
        # GPP-4323 does not provide a SCPI query for "max current" per channel.
        # If you need an absolute value, use the datasheet ratings.
        if channel == 1 or channel == 2:
            return 3
        elif channel == 3:
            return 1
        elif channel == 4:
            return 1
        #raise NotImplementedError(
        #    "GPP-4323 SCPI does not support querying maximum current; "
        #    "use the datasheet specs instead."
        #)

    def get_minimum_source_current(self, channel=1):
        # Minimum programmable current is effectively 0A.
        return 0

    def set_voltage_limit(self, channel, limit):
        # Map "voltage limit" to OVP threshold for this channel.
        self.check_channel(channel)
        ch = int(channel)
        self.visa_session.write(f":OUTPut{ch}:OVP {limit}")
        #self.visa_session.write("*WAI")
        return self.visa_session.query("*OPC?").strip() == "1"

    def get_voltage_limit(self, channel):
        self.check_channel(channel)
        ch = int(channel)
        limit = float(self.visa_session.query(f":OUTPut{ch}:OVP?"))
        return limit

    def get_maximum_source_voltage(self, channel=1):
        # No direct SCPI query; refer to datasheet for absolute maximum.
        # If you need an absolute value, use the datasheet ratings.
        if channel == 1 or channel == 2:
            return 32
        elif channel == 3:
            return 5
        elif channel == 4:
            return 15
        #raise NotImplementedError(
        #    "GPP-4323 SCPI does not support querying maximum voltage; "
        #    "use the datasheet specs instead."
        #)

    def get_minimum_source_voltage(self, channel=1):
        # Minimum programmable voltage is effectively 0V.
        return 0.0

    # ------------------------------------------------------------------
    # Measurements
    # ------------------------------------------------------------------
    def get_measured_voltage(self, channel):
        self.check_channel(channel)
        ch = int(channel)
        # VOUTX? returns actual output voltage
        #voltage = float(self.visa_session.query(f"VOUT{ch}?"))
        resp = self.visa_session.query(f"VOUT{ch}?").strip()
        voltage = float(resp.rstrip("V"))
        return voltage

    def get_all_measured_voltages(self):
        # Query all channel voltages
        voltages_str = self.visa_session.query(":MEASure:VOLTage:ALL?")
        voltages = [float(x) for x in voltages_str.split(",")]
        return voltages

    def get_measured_current(self, channel):
        self.check_channel(channel)
        ch = int(channel)
        resp = self.visa_session.query(f"IOUT{ch}?").strip()
        current = float(resp.rstrip("A"))
        return current

    def get_all_measured_currents(self):
        currents_str = self.visa_session.query(":MEASure:CURRent:ALL?")
        currents = [float(x) for x in currents_str.split(",")]
        return currents

    def get_measured_power(self, channel):
        self.check_channel(channel)
        ch = int(channel)
        power = float(self.visa_session.query(f":MEASure{ch}:POWEr?"))
        return power

    def get_all_measured_powers(self):
        powers_str = self.visa_session.query(":MEASure:POWEr:ALL?")
        powers = [float(x) for x in powers_str.split(",")]
        return powers
