
import sys,os
import machine
from machine import Pin
from machine import ADC
import network
import struct
import binascii
from micropython import const


# VERSION
VERSION = const(0x000000005)
REVISION = const(0)
BRD = b'BLING'

CALLEN_MODE = 0
CELESTE_MODE = 1

_MAC = network.WLAN().config('mac')
def get_mac32_from_wlan_mac():
    (mac32,) = struct.unpack('>I', _MAC[-4:])
    return mac32
ADDR = get_mac32_from_wlan_mac()
MAC = binascii.hexlify(_MAC,':').decode()

if MAC == 'dc:54:75:d8:6f:48':
    CLOCK_MODE = CELESTE_MODE
elif MAC == 'dc:54:75:d8:6f:58':
    CLOCK_MODE = CALLEN_MODE
else:
    CLOCK_MODE = CALLEN_MODE


def get_board_name_and_mcu_name():
    board_mcu = os.uname().machine.split('with')
    return (
        board_mcu[0].strip().encode(),
        board_mcu[1].strip().encode(),
    )

#get machine
(board_name, mcu_name) = get_board_name_and_mcu_name()

