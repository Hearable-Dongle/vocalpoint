from smbus2 import SMBus
import time

bus = SMBus(1)
ADDR=0x42
v_keep = 0

while True:
    v = bus.read_byte(ADDR)
    if v != v_keep:
        print("Volume from app:", v)
        v_keep=v