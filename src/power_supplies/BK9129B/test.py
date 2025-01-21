import pyvisa
rm = pyvisa.ResourceManager()
print(rm.list_resources())

visa_session = rm.open_resource('ASRL5::INSTR')

visa_session.timeout = 10000 # milliseconds
visa_session.read_termination = '\n'



# Put device into remote control mode
visa_session.write('SYST:REM')

# Set voltage to 5V
print(visa_session.query('SYST:VERS?'))
# visa_session.write('SYST:BEEP')
# print('*ESR?')
# print(visa_session.query('*ESR?'))
print('*TST?')
print(visa_session.query('*TST?'))
print(type(visa_session.query('*TST?')))

visa_session.write('*WAI')
print('*OPC?')
print(visa_session.query('*OPC?'))
# print(visa_session.query('[SOURce:]APPly:VOLTage[:LEVel][:IMMediate][:AMPLitude]?'))

visa_session.write('APP:VOLT 30,5')
visa_session.write('*WAI')
print('*OPC?')
print(visa_session.query('*OPC?'))
print(visa_session.query('APP:VOLT?'))


# visa_session.write('APP:CURR 0.3,1,2')
# visa_session.write('*WAI')
# print('*OPC?')
# print(visa_session.query('*OPC?'))
# print(visa_session.query('APP:CURR?'))


visa_session.write('APP:CURR 0.3,1,2')
visa_session.write('*WAI')
visa_session.write('CURR 10')
visa_session.write('*WAI')
visa_session.write('INST:NSEL 2')
visa_session.write('*WAI')
visa_session.write('CURR 0.01')
visa_session.write('*WAI')
# print('*OPC?')
print(visa_session.query('CURR?'))
visa_session.write('INST:NSEL 1')
visa_session.write('*WAI')
print(visa_session.query('CURR?'))

visa_session.write('VOLT:LIMIT 0.01')
visa_session.write('*WAI')
visa_session.write('VOLT:LIMIT 0.01')

# assert 0
print('CHAN:OUTP:STAT?')
print(visa_session.query('CHAN:OUTP:STAT?'))
visa_session.write('CHAN:OUTP:STAT 1')
visa_session.write('*WAI')
print('CHAN:OUTP:STAT?')
print(visa_session.query('CHAN:OUTP:STAT?'))
visa_session.write('*WAI')


print('MEAS:POW?')
print(visa_session.query('MEAS:POW?'))
visa_session.write('*WAI')
print('MEAS:VOLT?')
print(visa_session.query('MEAS:VOLT?'))
visa_session.write('*WAI')
print('MEAS:CURR?')
print(visa_session.query('MEAS:CURR?'))
visa_session.write('*WAI')


visa_session.write('CHAN:OUTP:STAT 0')
visa_session.write('*WAI')
print('CHAN:OUTP:STAT?')
print(visa_session.query('CHAN:OUTP:STAT?'))
visa_session.write('*WAI')


print(visa_session.query('INSTrument:SELect?'))


# # Set current to 1A
# visa_session.write('SOUR:CURR 1.0')

# # Enable the output. '1' or 'ON' for enable, '0' or 'OFF' for disable.
# visa_session.write('SOUR:OUTP:STAT 1')