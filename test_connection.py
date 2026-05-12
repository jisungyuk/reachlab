import serial
import time

port = 'COM1'
baud = 115200

try:
    ser = serial.Serial(port, baud, timeout=1)
    print(f"Connected to {port}")
    time.sleep(0.5)

    # Request continuous data
    ser.write(b'P')
    time.sleep(0.2)

    for i in range(10):
        line = ser.readline()
        if line:
            print(repr(line))
        time.sleep(0.1)

    ser.close()
except Exception as e:
    print(f"Error: {e}")
