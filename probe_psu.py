"""Diagnose PSU serial state. Tries IDN before TST so we can tell if
the BK9129B is alive but its self-test is stuck."""
import pyvisa, time

rm = pyvisa.ResourceManager()
print('VISA resources:', rm.list_resources())

s = rm.open_resource('ASRL5::INSTR')
s.timeout = 5000
s.read_termination = '\n'
s.write_termination = '\n'
s.baud_rate = 9600

# Drain any pending bytes
try:
    s.clear()
except Exception as e:
    print('clear() failed:', e)
time.sleep(0.2)

print('Sending *IDN?...')
try:
    idn = s.query('*IDN?')
    print(f'  IDN: {idn!r}')
except Exception as e:
    print('  IDN failed:', e)

print('Sending SYST:REM...')
try:
    s.write('SYST:REM')
    time.sleep(0.2)
except Exception as e:
    print('  SYST:REM failed:', e)

print('Sending *IDN? again after SYST:REM...')
try:
    idn = s.query('*IDN?')
    print(f'  IDN: {idn!r}')
except Exception as e:
    print('  IDN failed:', e)

print('Sending *TST?...')
try:
    s.timeout = 30000
    tst = s.query('*TST?')
    print(f'  TST: {tst!r}')
except Exception as e:
    print('  TST failed:', e)

s.close()
print('Done.')
