
import asyncio
import sys
import gc
import time
from micropython import const
import esp32
import io
import deflate

from asyncio import Event
from primitives.events import WaitAny
from primitives import Pushbutton

import machine
from machine import Pin
from neopixel import NeoPixel

import board

from wifi.wifi import Wifi
from wifi.wifi import WifiSocket

from mqtt.core import MQTTCore

from lib.ntptime import settime as ntp_settime
from lib.mytime import lcl_timetuple

import clock
from clock import clock_coro

from display import LED_HUE_PUPLE
from display import NEOPIXELS_LEN
from display import NEOPIXELS_ROW
from display import i_to_xy
from display import make_palette
from display import render
from display import render_solid


# pins
_NEOPIXELS_PWR = const(6)
_NEOPIXELS_DAT = const(18)

# 18
# 1111:111111:111111
# 1111
#     111111

MQTT_ROOT = b'kx5x'

PIN_BUTTON_A = const(11)
PIN_BUTTON_B = const(10)
PIN_BUTTON_C = const(33)
PIN_BUTTON_D = const(34)

async def gc_coro():
    try:
        while True:
            gc.collect()
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        raise
    except Exception as err:
        sys.print_exception(err)



# Hardware watchdog: if the event loop stalls for this long, the board reboots itself.
# Once started it can't be stopped, so while developing over USB (Ctrl-C into the REPL)
# set to 0 to disable. Must be longer than the longest blocking call (TLS handshake, NTP).
WDT_TIMEOUT_MS = 30000

async def wdt_coro():
    if not WDT_TIMEOUT_MS:
        return
    wdt = machine.WDT(timeout = WDT_TIMEOUT_MS)
    while True:
        wdt.feed()
        await asyncio.sleep_ms(2000)

async def mqtt_coro(wifi):
    rx_task = None
    retry_s = 1
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
                    retry_s = 1 # connected, reset the backoff
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
                rx_task = None
        # connection ended or failed: back off (1s, 2s, 4s ... max 60s) before reconnecting
        await asyncio.sleep(retry_s)
        retry_s = min(retry_s*2, 60)

async def mqtt_rx_coro(rx_q):
    part = esp32.Partition(esp32.Partition.RUNNING)
    part.mark_app_valid_cancel_rollback()
    ota_part = esp32.Partition(esp32.Partition.RUNNING).get_next_update()
    OTA_BLOCK_SIZE = 4096
    b = bytearray(OTA_BLOCK_SIZE)
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
                        # wbits=12 caps the window at 4KB (a page is 4KB uncompressed); without
                        # it the window size comes from the header, and zlib's default is 32KB
                        with deflate.DeflateIO(io.BytesIO(r.payload), deflate.ZLIB, 12) as d:
                            print('wr ota page:{}'.format(page))
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
        retry_s = 5
        while True:
            try:
                print('NTP | fetching time')
                ntp_settime()
                retry_s = 5
            except asyncio.CancelledError:
                raise
            except Exception as err:
                # offline, or DNS not ready yet: back off and retry instead of giving up
                print('NTP | failed, retry in {}s'.format(retry_s), repr(err))
                await asyncio.sleep(retry_s)
                # (can't use min() here, ntp_coro has a local named min below)
                retry_s = retry_s*2 if retry_s < 150 else 300
                continue
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

_FRAME_MS = const(8)    # neo.write() blocks ~10ms for 320 pixels, don't go faster
_HUE_MS   = const(10)   # ms per hue step (256 steps/cycle -> ~2.5s per cycle, was shift//20)

# colorize and write to neopixel
# colors come from precomputed palettes and render() fills the neopixel buffer without allocating
async def display_coro(frmmsk, neo):
    pal_day   = make_palette(val=5)
    pal_night = make_palette(val=1)
    acc = 0
    last = time.ticks_ms()
    try:
        while True:
            try:
                await asyncio.sleep_ms(_FRAME_MS)
                now = time.ticks_ms()
                acc = (acc + time.ticks_diff(now, last)) % (256*_HUE_MS)
                last = now
                if clock.is_nighttime:  # set by clock_coro
                    render_solid(neo.buf, frmmsk, pal_night, LED_HUE_PUPLE)
                elif board.CLOCK_MODE == board.CELESTE_MODE:
                    render(neo.buf, frmmsk, pal_day, acc//_HUE_MS)
                elif board.CLOCK_MODE == board.CALLEN_MODE:
                    yr, mth, day, hr, min, sec, msec, = lcl_timetuple()
                    render_solid(neo.buf, frmmsk, pal_day, (min*60+sec)*360//(60*60))
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

def test(p):
    print(f'hello {p}')

async def start():
    print(f'_MAC: {board._MAC}');
    print(f'MAC: {board.MAC}');
    
    for p in [PIN_BUTTON_A,PIN_BUTTON_B,PIN_BUTTON_C,PIN_BUTTON_D]:
        pin = Pin(p, Pin.IN)
        pb = Pushbutton(pin)
        pb.press_func(test, (p,))
    
    try:
        led_pwr = Pin(_NEOPIXELS_PWR, Pin.OUT, value=1)
        gc_task = asyncio.create_task(gc_coro())
        wdt_task = asyncio.create_task(wdt_coro())
        neo =NeoPixel(Pin(_NEOPIXELS_DAT), NEOPIXELS_LEN)
        framemask = bytearray(NEOPIXELS_LEN)

        # for x in range(NEOPIXELS_LEN):
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
        wdt_task.cancel()

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

