
import sys
from micropython import const
import machine
import gc

import upydash as _ 
import asyncio
from primitives import launch
import socket
import tls
import network
import time
import errno
import uctypes
from asyncio import Event
import binascii

import wifi.defs as wifi_defs

from lib.priorityqueue import PriorityQueue
from lib import cancel_gather_wait_for_ms


_BUSY_ERRORS = [errno.EINPROGRESS, errno.ETIMEDOUT, 118, 119]
_SOCKET_POLL_DELAY = const(10) #slow poll delay so we don't slam

#socket.getaddrinfo is blocking.  Keep global list of results so we don't block
#more than once
AddrInfos =[]

class WifiSocket():
    def __init__(self, ifce     = None,
                       host     = None, 
                       port     = None,
                       en_ssl   = True,
                       tx_q     = None,
                       ):
        self._name  = 'WIFISOCK'

        self.wifi = ifce
        # self.rtr_ifce = ifce
        self.sock = None
        self.host = host
        self.port  = port
        self.en_ssl = en_ssl
        self.addr_info = None

        self.rx_q   = PriorityQueue()

        # use provided tx_q, or create our own
        if not tx_q:
            self.tx_q   = PriorityQueue()
        else:
            self.tx_q   = tx_q
        # self.tx_q   = PriorityQueue()

        #track if a socket is open or closed, used for retry methods
        #don't set these directly, use set_socket_status(is_ready=
        # self.socket_down = Event()
        # self.socket_up   = Event()
        self.is_closed = Event()
        self.is_closed.set()

        #used by caller to determine if socket is good
        # self.is_ready = self.socket_up

        self.tasks        = [] 

        #stats
        self.ticks_start = time.ticks_ms()
        self.rx_count = 0    #rx bytes/sec
        self.tx_count = 0    #tx bytes/sec

    async def start(self):
        print('start')
        await self.stop_tasks()

        try:
            await asyncio.wait_for_ms(self.start_socket(),10000)
            self.tasks.append(asyncio.create_task(self.rx_coro()))
            self.tasks.append(asyncio.create_task(self.tx_coro()))
            self.tasks.append(asyncio.create_task(self.debug_coro()))
        except asyncio.CancelledError:
            raise
        except Exception as err:
            raise

    async def stop_tasks(self):
        try:
            await cancel_gather_wait_for_ms(tasks      = self.tasks,
                                            timeout_ms = 3000)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)
        finally:
            self.tasks.clear()

    async def stop(self, verbose=False):
        try:
            print('stop')
            self.is_closed.set()
            if self.sock:
                # self.debug('closing socket (stop)', id(self.sock))
                self.sock.close()
            await self.stop_tasks()
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

    async def start_socket(self):

        #get socket info
        tries = 3
        while True:
            print('start_socket: {}:{}'.format(self.host, self.port))
            try:
                addrinfo = self.get_socket_info(host = self.host,
                                                port = self.port,)
                break
            except asyncio.CancelledError:
                raise
            except OSError as e:
                if e.args[0] == -202:
                    tries -= 1
                    if tries == 0:
                        raise
                    await asyncio.sleep(1)

        self.sock = socket.socket()
        self.sock.setblocking(False)

        try:
            print('connect: {}'.format(addrinfo))
            self.sock.connect(addrinfo)
        except OSError as e:
            # esp32 https://github.com/micropython/micropython-esp32/issues/166
            if e.args[0] not in _BUSY_ERRORS:
                raise
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)
            await asyncio.sleep_ms(_SOCKET_POLL_DELAY)

        if self.en_ssl:
            print('start ssl 1')
            ctx = tls.SSLContext(tls.PROTOCOL_TLS_CLIENT)
            ctx.verify_mode = tls.CERT_OPTIONAL
            print('start ssl 2')
            gc.collect()
            self.sock = ctx.wrap_socket(self.sock)
            print('start ssl 3')

        # print('connected {}:{}'.format(self.host, self.port))

        self.is_closed.clear()


    async def rx_coro(self):
        try:
            #local access
            # socket_up = self.socket_up
            # socket_up_wait = self.socket_up.wait
            # socket_up_is_set = self.socket_up.is_set
            is_closed = self.is_closed.is_set
            rx_q = self.rx_q
            rx_q_put = rx_q.put
            sleep_ms = asyncio.sleep_ms

            #pre-allocate buffer
            max_len = 1024*5
            data = bytearray(max_len)
            mv = memoryview(data)

            # await socket_up_wait()
            # we get new sockets, after each socker up
            sock_readinto = self.sock.readinto 
            while True:
                if is_closed():
                    break
                await sleep_ms(_SOCKET_POLL_DELAY)
                n = sock_readinto(data)
                if n:
                    #we need to pass in a copy into the queue since we will overwrite the same buffer next iteration
                    await rx_q_put(bytes(mv[:n]))
                    self.rx_count += n
                    n = 0

            # await socket_up_wait()
            # sock_read = self.sock.read 
            # while True:
                # if not socket_up_is_set():
                    # break
                # await sleep_ms(_SOCKET_POLL_DELAY)
                # buff = None
                # try:
                    # # when reading, we always are reading in the bytes buffer
                    # # since we need to pass the copy to put
                    # # we don't need to read_into since we'd create a copy anyway
                    # buff = sock_read(max_len)
                    # if buff:
                        # await rx_q_put(buff)
                # except asyncio.CancelledError:
                    # raise

        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)
            # self.set_socket_status(is_ready = False)
            # self.update_gateway_ifce(is_ready = False) #immediately stop routing data to this gateway
            return
        finally:
            print('RX SOCK CLOSE', self.sock, id(self.sock))
            self.is_closed.set()

    async def tx_coro(self):
        try:
            #local access
            tx_q = self.tx_q
            tx_q_wait = tx_q.wait
            tx_q_empty = tx_q.empty
            tx_q_peek_len = tx_q.peek_len
            tx_q_get = tx_q.get_nowait
            # socket_up = self.socket_up
            # socket_up_is_set = socket_up.is_set
            # socket_down = self.socket_down
            # socket_down_is_set = socket_down.is_set
            is_closed = self.is_closed.is_set
            sleep_ms = asyncio.sleep_ms

            #pre-allocate buffer
            max_len = 1024*5
            data = bytearray(max_len)
            mv = memoryview(data)

            cnt = 0
            idx = 0
            errcnt = 0

            # await socket_up.wait()
            sock_write = self.sock.write
            while True:
                idx = 0
                cnt = 0
                # if not socket_up_is_set() or socket_down_is_set():
                    # raise Exception('Socket is closed')
                if is_closed():
                    break
                await tx_q_wait() #wait for item without getting item
                while True:
                    if tx_q_empty():
                        break
                    next_len = tx_q_peek_len()
                    if not next_len:
                        continue
                    if idx == 0 and next_len > max_len: #the data is bigger than the buffer -> grow the buffer
                        max_len = next_len
                        data = bytearray(max_len)
                        mv = memoryview(data)
                    if idx+next_len > max_len:
                        break
                    mv[idx:idx+next_len] = tx_q_get()
                    # print('tx_coro 1', next_len)
                    idx += next_len
                    cnt += 1
                n = 0
                while n < idx:
                    # write returns None if not successful instead of raising EAGAIN like send
                    r = sock_write(mv[n:idx])
                    if not r: #None or 0
                        print('tx_coro', r)
                        # await sleep_ms(100)
                        await sleep_ms(0)
                        errcnt += 1
                    else:
                        n += r
                        await sleep_ms(0) #release scheduling to asyncio
                    if errcnt > 3:
                        raise Exception('sock write errored out')

                #throughput
                self.tx_count += n

                    # alternative version with send.  send throws EAGAIN, requires a try block
                    # try:
                        # r = sock.send(mv[n:idx])
                        # if not r: #None or 0
                            # await sleep_ms(10)
                        # else:
                            # n += r
                            # await sleep_ms(0) #don't lock up
                    # except OSError as err:
                        # # sys.print_exception(err)
                        # if err.args[0] == errno.EAGAIN: #OSError: [Errno 11] EAGAIN
                            # #socket busy
                            # await sleep_ms(10)

        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)
        finally:
            print('TX SOCK CLOSE', self.sock, id(self.sock))
            self.is_closed.set()
            # self.set_socket_status(is_ready = False)

            # TODO, this is an issue, this interferes with the NEXT connection attempt, sending data out of sequence
            # self.tx_q._p_queue = [] #clear the priority queue
            # if idx:
                # self.tx_q._queue.insert(0,bytes(mv[:idx])) #add unsent items back into queue


    def get_socket_info(self, host, port):
        # Note this blocks if DNS lookup occurs. Do it once to prevent
        # blocking during later internet outage:
        addrinfo = _.find(AddrInfos, lambda addrinfo: addrinfo.host == host and addrinfo.port == port)
        # addrinfo = None # always do DNS lookup
        if not addrinfo:
            addrinfo = wifi_defs.AddrInfo(
                host      = host,
                port      = port,
                addrinfo = socket.getaddrinfo(host, port)[0][-1],
            )
            AddrInfos.append(addrinfo)
        return addrinfo.addrinfo


    # def set_socket_status(self, is_ready):
        # if is_ready:
            # self.socket_down.clear()
            # self.socket_up.set()
        # else:
            # self.socket_down.set()
            # self.socket_up.clear()

    async def debug_coro(self):
        #local access optimization
        sleep = asyncio.sleep

        try:
            while True:
                await sleep(10)
                #throughput report
                ticks = time.ticks_diff(time.ticks_ms(), self.ticks_start)
                await print( 'RX B/s',round(self.rx_count/(ticks/1000),1),
                              'TX B/s',round(self.tx_count/(ticks/1000),1),)
                self.ticks_start = time.ticks_ms()
                self.rx_count = 0
                self.tx_count = 0
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)


class Wifi():
    def __init__(self, addr     = None,
                       rtr_in_q = None,
                       # rtc      = None,
                       broker   = None,
                       ):
        self._name  = 'WIFI'

        self.bro = broker
        if self.bro:
            self.bro.subscribe(self._name.lower(), self.on_bro_msg)

        self.addr     = addr

        self.sta = network.WLAN(network.STA_IF)
        self.mac  = self.sta.config('mac')

        #don't set these directly, use set_connected_ap(is_connectped=
        # self._ap_connected = Event()
        # self._ap_not_connected = Event()
        self.is_closed = Event()
        self.is_closed.set()

        self.tasks = []

    # process brokered messages
    async def on_bro_msg(self, topic, msg, *args):
        try:
            evt, params = msg
            if fn := getattr(self, evt) if hasattr(self, evt) else None:
                launch(fn, params) # launch with sync or async
                return
            print('SKIP MSG topic:{} event:{} params:{}'.format(topic, evt, params))
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)

    @property
    def client_id(self):
        return binascii.hexlify(self.mac).decode()

    async def start(self):
        print('start')
        await self.stop_tasks()
        # self.sta.active(True)

        try:
            await asyncio.wait_for_ms(self.connect(),30000)
        except asyncio.TimeoutError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as err:
            raise

    async def stop_tasks(self):
        try:
            await cancel_gather_wait_for_ms(tasks      = self.tasks,
                                            timeout_ms = 3000)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)
        finally:
            self.tasks.clear()

    async def stop(self, verbose=False):
        try:
            print('stop')
            self.is_closed.set()
            await self.stop_tasks()
            # await super().stop_tasks()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err)
        finally:
            self.sta.active(False)
            # seem to sometimes is connect if we reactivate too fast
            # pause here
            await asyncio.sleep(1)

    async def __aenter__(self):
        try:
            await self.start()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            sys.print_exception(err) # display error at gtw 
            await self.stop()
            raise
        return self

    async def __aexit__(self, *args):
        await self.stop()

    async def connect(self):
        # print('conn_coro', 'start')
        tx_power = wifi_defs.WIFI_TX_POWER
        try:
            if len(wifi_defs.APs) == 0:
                raise Exception('no aps')
            # tx_power = tx_power if tx_power >= wifi_defs.WIFI_TX_MIN_POWER else wifi_defs.WIFI_TX_MIN_POWER
            await self.connect_knownap(verbose=True)
            # if self.sta.status() != network.STAT_GOT_IP:
            if not self.sta.isconnected():
                print('ip failed', 'self.sta.status', self.sta.status(), network.STAT_GOT_IP, 'tx power', tx_power)
                raise Exception('failed to connect')
                # tx_power -= 1
                # continue

            #connected!
            # tx_power = wifi_defs.WIFI_TX_POWER
            print('ip', self.ip())
            self.is_closed.clear()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            raise

    async def connect_knownap(self, verbose=False):
        try:
            while True:
                for ssid,passw in wifi_defs.APs:
                    self.sta.active(False)
                    self.sta.active(True)
                    print('trying to connect to {}'.format(ssid))
                    # self.sta.connect('ThunderFace2', 'sararocksmyworld')
                    self.sta.connect(ssid,passw)
                    print('txpower:{}'.format(wifi_defs.WIFI_TX_POWER))
                    self.sta.config(txpower = wifi_defs.WIFI_TX_POWER)
                    self.sta.config(pm = self.sta.PM_POWERSAVE)
                    # self.sta.config(pm = self.sta.PM_PERFORMANCE)
                    await asyncio.sleep_ms(1000)
                    start = time.ticks_ms()
                    # while time.ticks_diff(time.ticks_ms(), start) < 10000 and\
                            # not self.sta.isconnected():
                    while time.ticks_diff(time.ticks_ms(), start) < 10000 and\
                            not self.sta.isconnected() and\
                            self.sta.status() not in [network.STAT_NO_AP_FOUND, network.STAT_WRONG_PASSWORD]:
                        print(self.sta.isconnected(), self.sta.status())
                        await asyncio.sleep_ms(1000)
                    await asyncio.sleep_ms(1000)
                    if self.sta.isconnected():
                        print('CONNECTED to {}'.format(ssid))
                        return 
                    self.sta.disconnect()
                    await asyncio.sleep_ms(1000)
            # await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            raise

    # async def connect_knownap(self, verbose=False):
        # try:
            # # super annoying block wifi scan
            # # would be cool if non-blocking scan introduced....
            # # https://github.com/micropython/micropython/pull/7526
            # print('wifi scan...')
            # scan_results = self.sta.scan()
            # #scan result tuple (ssid, bssid, channel, RSSI, security, hidden)
            # scan_results = _.sort_by(scan_results, lambda r: r[3])
            # self.sta.disconnect() 
            # for scan_ap in scan_results[::-1]:
                # print('wifi scan',scan_ap)
                # for ap in wifi_defs.APs:
                    # my_ssid = ap[0]
                    # scan_ssid = scan_ap[0]
                    # mv = memoryview(scan_ssid)
                    # if my_ssid == mv[:len(my_ssid)]:
                        # if verbose:
                            # print('trying', scan_ssid, ap[1])
                        # self.sta.connect(scan_ssid, ap[1])
                        # start = time.ticks_ms()
                        # while time.ticks_diff(time.ticks_ms(), start) < 10000 and not self.sta.isconnected():
                            # await asyncio.sleep_ms(250)
                        # if self.sta.isconnected():
                            # print('connected to', scan_ssid, ap[1])
                            # return 
            # # await asyncio.sleep(5)
        # except asyncio.CancelledError:
            # raise
        # except Exception as err:
            # raise

    def ip(self):
        try:
            return self.sta.ifconfig()[0]
        except asyncio.CancelledError:
            raise
        except:
            return '0.0.0.0'
        
    async def iq_gtws_ready(self, gtws_ready):
        pass

