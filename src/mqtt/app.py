
import sys
import upydash as _ 
import asyncio
import ujson
import uctypes

import defs

from asyncio import Event
from primitives.delay_ms import Delay_ms

import encdec
import encdec.defs as encdec_defs

from debug import DebugMixin
from lib import byteify_pkt
from lib import cancel_gather_wait_for_ms

# <org_id>/up -- devices upload data here
# <org_id>/dn -- commands sent to devices here

class MQTTApp(DebugMixin):
    def __init__(self, addr,
                       org_id,
                       rtr_out_q,   # router egress
                       rtr_in_q,    # router ingress
                       mqtt,
                       debug   = None,
                       ):

        self._name  = 'MQTTApp'
        self._debug = debug

        self.addr = addr
        self.org_id = org_id
        self.mqtt = mqtt
        self.rtr_out_q = rtr_out_q
        self.rtr_in_q = rtr_in_q

        self.is_closed = Event()
        self.is_closed.set()

        #Set interface
        self.publish = self.mqtt.publish
        self.pub_topic = b'{}/up'.format(self.org_id)
        self.subscribe = self.mqtt.subscribe
        self.unsubscribe = self.mqtt.unsubscribe
        self.rx_q = self.mqtt.mqtt_app_rx_q

        # # Router management
        # self.subscribed_addrs = [] # router topic subs

        self.tasks = []
        # self.wait_for_room_task = None

    async def start(self):
        self.debug('start')
        await self.stop_tasks()

        self.is_closed.clear()

        #wait until the room is confirmed up and ready
        qosack = await self.subscribe(
            qoss   = 1,
            topics = [ 
                b'{}/dn'.format(self.org_id,)
            ],
        )
        try:
            await self.adebug('wait for suback')
            await asyncio.wait_for_ms(qosack.event.wait(), 3000)
        except asyncio.TimeoutError as err:
            raise

        self.tasks.append(asyncio.create_task(self.rx_coro()))

    async def stop_tasks(self):
        try:
            await cancel_gather_wait_for_ms(tasks      = self.tasks,
                                            timeout_ms = 5000)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)
        finally:
            self.tasks.clear()

    async def stop(self, verbose=False):
        try:
            await self.adebug('stop')
            self.subs = []

            await self.stop_tasks()
            # await super().stop_tasks()

        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)

    async def __aenter__(self):
        try:
            await self.start()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)
            await self.stop()
            raise
        return self

    async def __aexit__(self, *args):
        await self.stop()

    async def post_got_room(self):
        #actually start routing data to the room
        await self.adebug('post_got_room')

        self.tasks.append(asyncio.create_task(self.rtr_out_coro()))
        await self.update_routing_addrs(routing_addrs = [])

    async def rx_coro(self):
        #local access
        BIG_ENDIAN = uctypes.BIG_ENDIAN
        cCmdHeader = encdec_defs.cCmdHeader
        addressof = uctypes.addressof
        _struct = uctypes.struct
        is_closed = self.is_closed.is_set

        try:
            while True:
                if is_closed():
                    break

                ##################################################
                # GET DATA FROM CORE (self.mqtt.mqtt_app_rx_q) AND PROCESS
                pubpkt = await self.rx_q.get()
                #pubpkt of type Publish_struct (named tuple)
                await self.process_pkt(pubpkt = pubpkt)
                ##################################################

        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)
        finally:
            self.is_closed.set()

    async def process_pkt(self, pubpkt):
        try:
            #we received an inbound command

            ##################################################
            # passing RX data into RTR
            await self.rtr_in_q.put(pubpkt.payload, 
                                    is_priority    = True, #inbound messages from server to front of line
                                    )
            ##################################################
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)


    async def rtr_out_coro(self):

        addr = self.addr
        # pringer_trigger = self.pinger.trigger
        publish = self.publish
        rtr_out_q_get = self.rtr_out_q.get
        pub_topic = self.pub_topic

        try:
            while True:
                ipkt = await rtr_out_q_get()
                await publish(topic   = pub_topic,
                              payload = byteify_pkt(ipkt),
                              qos     = 0,
                              )
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)
        finally:
            self.is_closed.set()

    async def update_routing_addrs(self, routing_addrs):
        # await self.adebug('update_routing_addrs', routing_addrs)
        if self.addr not in routing_addrs:
            routing_addrs.append(self.addr)
