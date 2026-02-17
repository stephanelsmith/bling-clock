
import sys,os
import machine
from machine import Pin
from machine import ADC
import network
import struct
import collections
import esp32
import binascii
from micropython import const


# VERSION
VERSION = const(0x000000005)
REVISION = const(0)
BRD = b'BLING'

_MAC = network.WLAN().config('mac')
def get_mac32_from_wlan_mac():
    (mac32,) = struct.unpack('>I', _MAC[-4:])
    return mac32
ADDR = get_mac32_from_wlan_mac()
MAC = binascii.hexlify(_MAC,':').decode()

def get_board_name_and_mcu_name():
    board_mcu = os.uname().machine.split('with')
    return (
        board_mcu[0].strip().encode(),
        board_mcu[1].strip().encode(),
    )

#get machine
(board_name, mcu_name) = get_board_name_and_mcu_name()


def is_vbus():
    return True
