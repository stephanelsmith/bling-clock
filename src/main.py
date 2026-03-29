
import asyncio
import sys
import gc
from micropython import const
import esp32
import io
import deflate

from asyncio import Event
from primitives.events import WaitAny

import machine
from machine import Pin
from neopixel import NeoPixel
from font import char_to_pixels

import board

from wifi.wifi import Wifi
from wifi.wifi import WifiSocket

from mqtt.core import MQTTCore

from lib.ntptime import settime as ntp_settime
from lib.mytime import lcl_timetuple


CALLEN_MODE = 0
CELESTE_MODE = 1
CLOCK_MODE = CALLEN_MODE

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

MQTT_ROOT = b'ki5tof'


is_nighttime = False

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

# 0,0 top left
@micropython.viper
def xy_to_i(x:int, y:int) -> int:
    return x+y*_NEOPIXELS_ROW
@micropython.viper
def i_to_xy(i:int):
    return (i % _NEOPIXELS_ROW, i // _NEOPIXELS_ROW)


def write_text(frmmsk, text:bytes, jright=True, hue=LED_HUE_LIGHTBLUE, val=5):
    j = max(_NEOPIXELS_MAX_CHARS-len(text),0)
    if jright:
        text = b' '*j+text
    else:
        text = text + b' '*j
    for i in range(_NEOPIXELS_LEN):
        frmmsk[i] = 0
    for i,c in enumerate(text[:_NEOPIXELS_MAX_CHARS]):
        ps = char_to_pixels(c) # get character
        for x,p in enumerate(ps): # for each column
            for y in range(8): # for each row
                v = val if p&(0x01<<y) else 0
                # neo[xy_to_i(i*8+x, y)] = hsv_to_rgb(hue, 255, v)
                frmmsk[xy_to_i(i*8+x, y)] = 1 if p&(0x01<<y) else 0


async def mqtt_coro(wifi):
    rx_task = None
    while True:
        try:
            use_ssl = True
            async with WifiSocket(ifce   = wifi,
                                  host   = 'broker.hivemq.com',
                                  en_ssl = use_ssl,
                                  port   = 8883,
                                  ) as wifisocket:
                async with MQTTCore(socket    = wifisocket,
                                    client_id = wifi.client_id,
                                    ) as mqtt:
                    await mqtt.subscribe(topics = [MQTT_ROOT+b'/#'])
                    rx_task = asyncio.create_task(mqtt_rx_coro(rx_q = mqtt.mqtt_app_rx_q))
                    await WaitAny((
                        wifi.is_closed,
                        wifisocket.is_closed,
                        mqtt.is_closed,
                    )).wait()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)
        finally:
            if rx_task:
                rx_task.cancel()

async def mqtt_rx_coro(rx_q):
    part = esp32.Partition(esp32.Partition.RUNNING)
    part.mark_app_valid_cancel_rollback()
    ota_part = esp32.Partition(esp32.Partition.RUNNING).get_next_update()
    OTA_BLOCK_SIZE = 4096
    while True:
        try:
            r = await rx_q.get()
            if r:
                # print('RX',r)
                tlvls = r.topic.split(b'/')
                if tlvls[1] == b'ota':
                    if tlvls[2] == b'done':
                        print('OTA DONE RESETTING@')
                        ota_part.set_boot()
                        machine.reset()
                        # EXIT
                    page = int(tlvls[2].decode())
                    try:
                        with deflate.DeflateIO(io.BytesIO(r.payload), deflate.ZLIB) as d:
                            print('wr ota page:{}'.format(page))
                            b = bytearray(OTA_BLOCK_SIZE)
                            d.readinto(b)
                            ota_part.writeblocks(page, b)
                    except Exception as err:
                        sys.print_exception(err)
                else:
                    print('Unkown message received',r)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)

# update the systemt time
async def ntp_coro():
    try:
        while True:
            print('NTP | fetching time')
            ntp_settime()
            for x in range(3600_000//5000):
                try:
                    await asyncio.sleep_ms(5000)
                    yr, mth, day, hr, min, sec, msec, = lcl_timetuple()
                    if yr < 2026:
                        break
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    sys.print_exception(err)
    except asyncio.CancelledError:
        raise
    except Exception as err:
        sys.print_exception(err)

# draw the clock into the framebuf as a mask
async def clock_coro(frmmsk):
    global is_nighttime
    prv_sec = None
    try:
        while True:
            try:
                await asyncio.sleep_ms(250)
                yr, mth, day, hr, min, sec, msec, = lcl_timetuple()
                is_nighttime = hr <= 8 or hr >= 19
                if yr < 2026:
                    if sec%2==0:
                        write_text(frmmsk = frmmsk,
                                   text = b'hello')
                    else:
                        if CLOCK_MODE == CALLEN_MODE:
                            write_text(frmmsk  = frmmsk,
                                    text = b'Calln')
                        elif CLOCK_MODE == CELESTE_MODE:
                            write_text(frmmsk  = frmmsk,
                                    text = b'Celst')
                    await asyncio.sleep_ms(1000)
                    continue
                # if prv_sec != sec:
                    # print('CLK','|',lcl_timetuple())
                    # prv_sec = sec
                sep = ':' if sec%2==0 else ' '
                time = '{:02}{}{:02}'.format(hr,sep,min)
                hue = (min*60+sec)*360//(60*60)
                val = 1 if (hr < 8 or hr > 19) else 5
                write_text(frmmsk  = frmmsk,
                           text    = time.encode(),
                           )
            except asyncio.CancelledError:
                raise
            except Exception as err:
                sys.print_exception(err)
    except asyncio.CancelledError:
        raise
    except Exception as err:
        sys.print_exception(err)

# colorize and write to neopixel
async def display_coro(frmmsk, neo):
    global is_nighttime
    shift = 0
    speed = 1
    try:
        while True:
            try:
                await asyncio.sleep_ms(3)
                yr, mth, day, hr, min, sec, msec, = lcl_timetuple()
                shift += speed
                for i in range(_NEOPIXELS_LEN):
                    x,y = i_to_xy(i)
                    if is_nighttime:
                        hue = LED_HUE_PUPLE
                        val = 1
                    elif CLOCK_MODE == CELESTE_MODE:
                        hue = ((x-shift//20)*256)//_NEOPIXELS_ROW
                        val = 5
                    elif CLOCK_MODE == CALLEN_MODE:
                        hue = (min*60+sec)*360//(60*60)
                        val = 5
                    val = val if frmmsk[i] else 0
                    neo[i] = hsv_to_rgb(hue, 255, val)
                neo.write()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                sys.print_exception(err)
    except asyncio.CancelledError:
        raise
    except Exception as err:
        sys.print_exception(err)

async def repl_coro():
    sreader = asyncio.StreamReader(sys.stdin.buffer)
    try:
        while True:
            try:
                l = await sreader.readline()
                s = l.decode()
                print('>{}'.format(l))
                if b'bootloader' in l:
                    machine.bootloader()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                sys.print_exception(err)
    except asyncio.CancelledError:
        raise
    except Exception as err:
        sys.print_exception(err)


async def start():
    print(f'_MAC: {board._MAC}');
    print(f'MAC: {board.MAC}');
    
    try:
        led_pwr = Pin(_NEOPIXELS_PWR, Pin.OUT, value=1)
        gc_task = asyncio.create_task(gc_coro())
        neo = NeoPixel(Pin(_NEOPIXELS_DAT), _NEOPIXELS_LEN)
        framemask = bytearray(_NEOPIXELS_LEN)

        # for x in range(_NEOPIXELS_LEN):
            # neo[x] = hsv_to_rgb(LED_HUE_RED, 255, 5)
        # neo[0] = hsv_to_rgb(LED_HUE_BLUE, 255, 5)
        # neo[1] = hsv_to_rgb(LED_HUE_GREEN, 255, 5)
        # neo.write()

        repl_task = asyncio.create_task(repl_coro())
        clock_task = asyncio.create_task(clock_coro(frmmsk = framemask))
        display_task = asyncio.create_task(display_coro(frmmsk = framemask,
                                                        neo = neo))

        while True:
            try:
                async with Wifi(addr = b'{}'.format(board.ADDR),
                                ) as wifi:
                    ntp_task = asyncio.create_task(ntp_coro())
                    mqtt_task = asyncio.create_task(mqtt_coro(wifi = wifi))
                    await Event().wait()
            except Exception as err:
                sys.print_exception(err)
                await asyncio.sleep(1)
                machine.reset()
            except KeyboardInterrupt:
                pass
            finally:
                await asyncio.sleep(3)
                if ntp_task:
                    ntp_task.cancel()
                if mqtt_task:
                    mqtt_task.cancel()
    finally:
        led_pwr.value(0)
        repl_task.cancel()
        clock_task.cancel()
        display_task.cancel()
        gc.collect()
        gc_task.cancel()

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

