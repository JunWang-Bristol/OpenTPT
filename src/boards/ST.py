import pyvisa
import ast
from board import Board


class ST(Board):
    def __init__(self, port):
        rm = pyvisa.ResourceManager()
        # print("rm.list_resources()")
        # print(rm.list_resources())
        if 'COM' in port:
            port = port.split('COM')[1]

        self.visa_session = rm.open_resource(f'ASRL{port}::INSTR')

        self.visa_session.timeout = 1000  # milliseconds
        self.visa_session.read_termination = '\n'
        self.visa_session.write_termination = '\n'
        self.visa_session.data_bits = 8
        self.visa_session.baud_rate = 115200
        self.visa_session.stop_bits = pyvisa.constants.StopBits.one
        self.visa_session.parity = pyvisa.constants.Parity.none

    def reset(self):
        self.visa_session.write('*RST')

    def get_identification(self):
        return self.visa_session.query('*IDN?\n')

    def get_version(self):
        return self.visa_session.query('SYST:VERS?')

    def add_pulse(self, pulse_period):
        # Validation should be done by the caller to avoid excessive SCPI queries
        self.visa_session.write(f'CONF:PUL:ADD {pulse_period}')

    def clear_pulses(self):
        self.visa_session.write('CONF:PUL:CLEAR')

    def read_pulses(self):
        return ast.literal_eval(f"[{self.visa_session.query('CONF:PUL?')}]")

    def run_pulses(self, number_repetitions=1):
        self.visa_session.write(f'APP:PUL:RUN {number_repetitions}')
        # try:
        #     while True:
        #         data = self.visa_session.read_raw()
        #         print(data)
        # except pyvisa.errors.VisaIOError as e:
        #     print(e)
        # result = None
        # while result != "1":
        #     print(result)
        #     result = self.visa_session.query('*OPC?').rstrip('\r')

    def count_trains(self):
        return int(self.visa_session.query('APP:PUL:COUNT?').rstrip('\r'))

    def get_minimum_period(self):
        return float(self.visa_session.query('CONF:PUL:MIN?').rstrip('\r'))

    def get_maximum_period(self):
        return float(self.visa_session.query('CONF:PUL:MAX?').rstrip('\r'))

    def flush_buffer(self):
        """Read and discard any data in the read buffer."""
        try:
            # Set a short timeout for flushing
            old_timeout = self.visa_session.timeout
            self.visa_session.timeout = 100
            while True:
                self.visa_session.read_raw()
        except pyvisa.errors.VisaIOError:
            pass  # Timeout expected when buffer is empty
        finally:
            self.visa_session.timeout = old_timeout

    def close(self):
        self.visa_session.close()


class NUCLEO_H503RB(ST):
    def __init__(self, port):
        super().__init__(port)
