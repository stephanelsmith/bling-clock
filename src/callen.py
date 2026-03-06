

import asyncio
import sys
import gc
from micropython import const
from random import randint
import esp32

from asyncio import Event
from primitives.events import WaitAny

import machine
from machine import Pin
from neopixel import NeoPixel
from font import char_to_pixels
from images.images import titan_logo
from images.images import mrr_logo

import board

from wifi.wifi import Wifi
from wifi.wifi import WifiSocket

from mqtt.core import MQTTCore
from mqtt.defs import LOBBY_PASSWORD

from board import ADDR

_NEOPIXELS_PWR = const(6)
_NEOPIXELS_DAT = const(18)
_NEOPIXELS_LEN = const(320)
_NEOPIXELS_ROW = const(40)
_NEOPIXELS_MAX_CHARS = const(5)

# hue
LED_HUE_RED       = const(0)
LED_HUE_REDORA    = const(5)
LED_HUE_ORANGE    = const(20)
LED_HUE_YELLOW    = const(45)
LED_HUE_GREEN     = const(85)
LED_HUE_TEAL      = const(130)
LED_HUE_LIGHTBLUE = const(160)
LED_HUE_BLUE      = const(165)
LED_HUE_DARKBLUE  = const(170)
LED_HUE_PUPLE     = const(175)
LED_HUE_PINK      = const(220)

async def gc_coro():
    try:
        while True:
            gc.collect()
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        raise
    except Exception as err:
        sys.print_exception(err)

@micropython.viper
def hsv_to_rgb(h:int, s:int, v:int):
    #adapted from c example
    h %= 256
    s %= 256
    v %= 256
    reg:int = h // 43 #region  255/6
    rem:int = (h - (reg * 43)) * 6 #remainder
    p:int = (v * (255 - s)) >> 8
    q:int = (v * (255 - ((s * rem) >> 8))) >> 8
    t:int = (v * (255 - ((s * (255 - rem)) >> 8))) >> 8
    if reg == 0:
        return (v, t, p)
    if reg == 1:
        return (q, v, p)
    if reg == 2:
        return (p, v, t)
    if reg == 3:
        return (p, q, v)
    if reg == 4:
        return (t, p, v)
    if reg == 5:
        return (v, p, q)

# x,y top left
@micropython.viper
def xy_to_i(x:int, y:int) -> int:
    return x+y*_NEOPIXELS_ROW
@micropython.viper
def i_to_xy(i:int):
    return (i % _NEOPIXELS_ROW, i // _NEOPIXELS_ROW)

def write_text(neo, text:bytes, jright=True, hue=LED_HUE_LIGHTBLUE):
    j = max(_NEOPIXELS_MAX_CHARS-len(text),0)
    if jright:
        text = b' '*j+text
    else:
        text = text + b' '*j
    for i,c in enumerate(text[:_NEOPIXELS_MAX_CHARS]):
        ps = char_to_pixels(c) # get character
        for x,p in enumerate(ps): # for each column
            for y in range(8): # for each row
                v = 5 if p&(0x01<<y) else 0
                neo[xy_to_i(i*8+x, y)] = hsv_to_rgb(hue, 255, v)


def draw_bytes(neo, bs:bytes, hue=LED_HUE_LIGHTBLUE):
    for i in range(8*40):
        b = bs[i//8]
        v = 5 if b&(0x80>>(i%8)) else 0
        x = i%40
        y = i//40
        neo[xy_to_i(x, y)] = hsv_to_rgb(hue, 255, v)


async def start():
    
    while True:
        try:
            led_pwr = Pin(_NEOPIXELS_PWR, Pin.OUT, value=1)
            gc_task = asyncio.create_task(gc_coro())
            rx_task = None
            
            neo = NeoPixel(Pin(_NEOPIXELS_DAT), _NEOPIXELS_LEN)

            write_text(neo  = neo,
                       text = b'lion')
            neo.write()

            await Event().wait()

        except Exception as err:
            sys.print_exception(err)
            await asyncio.sleep(1)
            machine.reset()
        except KeyboardInterrupt:
            pass
        finally:
            await asyncio.sleep(3)
            led_pwr.value(0)
            if rx_task:
                rx_task.cancel()
            gc.collect()
            gc_task.cancel()



print("lion")


def main():
    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        pass
    except Exception as err:
        sys.print_exception(err)
    finally:
        asyncio.new_event_loop()  # Clear retained state

main()

