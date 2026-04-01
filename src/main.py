
import asyncio
import sys
import gc
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

from clock import clock_coro

from display import NEOPIXELS_LEN
from display import NEOPIXELS_ROW
from display import i_to_xy
from display import hsv_to_rgb

CALLEN_MODE = 0
CELESTE_MODE = 1
if board.MAC == 'dc:54:75:d8:6f:48':
    CLOCK_MODE = CELESTE_MODE
elif board.MAC == 'dc:54:75:d8:70:38':
    CLOCK_MODE = CALLEN_MODE
else:
    CLOCK_MODE = CALLEN_MODE

# pins
_NEOPIXELS_PWR = const(6)
_NEOPIXELS_DAT = const(18)

# 18
# 1111:111111:111111
# 1111
#     111111

MQTT_ROOT = b'ki5tof'

PIN_BUTTON_A = const(11)
PIN_BUTTON_B = const(10)
PIN_BUTTON_C = const(33)
PIN_BUTTON_D = const(34)

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
                for i in range(NEOPIXELS_LEN):
                    x,y = i_to_xy(i)
                    if is_nighttime:
                        hue = LED_HUE_PUPLE
                        val = 1
                    elif CLOCK_MODE == CELESTE_MODE:
                        hue = ((x-shift//20)*256)//NEOPIXELS_ROW
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
        neo = NeoPixel(Pin(_NEOPIXELS_DAT), NEOPIXELS_LEN)
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

