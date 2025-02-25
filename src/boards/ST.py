import pyvisa
import ast
from board import Board


class ST(Board):
    def __init__(self, port):
        rm = pyvisa.ResourceManager()
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

        # # Put device into remote control mode
        # self.visa_session.write('SYST:REM')
        # self.visa_session.write('*WAI')

        # test = self.visa_session.query('*TST?')
        # assert test == "0", f"Initial test return fail: {test}"

        # self.voltages = None
        # self.channels = None

    def reset(self):
        self.visa_session.write('*RST')
        data = self.visa_session.read_raw()
        print(data)

    def get_identification(self):
        return self.visa_session.query('*IDN?\n')

    def get_version(self):
        return self.visa_session.query('SYST:VERS?')

    def add_pulse(self, pulse):
        self.visa_session.write(f'CONF:PUL:ADD {pulse}')

    def clear_pulses(self):
        self.visa_session.write('CONF:PUL:CLEAR')

    def read_pulses(self):
        return ast.literal_eval(f"[{self.visa_session.query('CONF:PUL?')}]")

    def run_pulses(self, number_repetitions=1):
        self.visa_session.write(f'CONF:PUL:RUN {number_repetitions}')

    def count_trains(self):
        return int(self.visa_session.query('CONF:PUL:COUNT?').rstrip('\r'))

    def get_minimum_period(self):
        return float(self.visa_session.query('CONF:PUL:MIN?').rstrip('\r'))

    def close(self):
        self.visa_session.close()


class NUCLEO_H503RB(ST):
    def __init__(self, port):
        super().__init__(port)
