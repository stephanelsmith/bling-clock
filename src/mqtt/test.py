
import asyncio
import sys
import gc

from primitives.events import WaitAny

from board import ADDR

from wifi.wifi import Wifi
from wifi.wifi import WifiSocket

from mqtt.core import MQTTCore
from mqtt.defs import LOBBY_PASSWORD

async def gc_coro():
    try:
        while True:
            gc.collect()
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        raise
    except Exception as err:
        sys.print_exception(err)

async def mqtt_rx_coro(rx_q):
    try:
        while True:
            r = await rx_q.get()
            if r:
                print('RX',r)
    except asyncio.CancelledError:
        raise
    except Exception as err:
        sys.print_exception(err)

async def start():
    try:
        gc_task = asyncio.create_task(gc_coro())
        rx_task = None

        async with Wifi(addr = b'{}'.format(ADDR),
                        ) as wifi:
            use_ssl = True
            # async with WifiSocket(ifce   = wifi,
                                  # host   = 'broker.hivemq.com',
                                  # en_ssl = use_ssl,
                                  # port   = 8883 if use_ssl else 1883,
                                  # ) as sock:
                # async with MQTTCore(socket    = sock,
                                    # client_id = wifi.client_id,
                                    # ) as mqtt:
            async with WifiSocket(ifce   = wifi,
                                  host   = b'lby.titanstats.io',
                                  en_ssl = use_ssl,
                                  port   = 8883 if use_ssl else 1883,
                                  ) as sock:
                async with MQTTCore(socket    = sock,
                                    client_id = wifi.client_id,
                                    username   = b'{}'.format(ADDR),
                                    password   = LOBBY_PASSWORD,
                                    ) as mqtt:
                    rx_task = asyncio.create_task(mqtt_rx_coro(rx_q = mqtt.mqtt_app_rx_q))
                    await mqtt.subscribe(topics = [b'd/{}'.format(ADDR)])
                    await WaitAny((
                        wifi.is_closed,
                        sock.is_closed,
                        mqtt.is_closed,
                    )).wait()
    except Exception as err:
        sys.print_exception(err)
    finally:
        if rx_task:
            rx_task.cancel()
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
