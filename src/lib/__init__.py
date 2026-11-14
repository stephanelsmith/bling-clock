# Helpers used by wifi/ and mqtt/, from titan-upyesp32s (upyesp32s/lib/__init__.py).
# Only the pieces bling-clock imports (and what they depend on) are included.

import asyncio
import uctypes

def byteify_pkt(pkt):
    if isinstance(pkt, (bytes, bytearray)):
        return pkt
    elif isinstance(pkt, uctypes.struct): #ctypes
        return bytes(pkt)
    elif hasattr(pkt, 'pkt'):
        return byteify_pkt(pkt.pkt)
    # elif isinstance(pkt, str):
        # return bytes(pkt,'utf8')
        # # return pkt
    # elif isinstance(pkt, (list, dict)):
        # j = ujson.dumps(pkt) #convert object to string
        # return bytes(j,'utf8')
    else:
        raise Exception('CANT BYTIFY PKT {}'.format(pkt))


def repr_task(task):
    res  = ':done' if task.done() else ':up'
    return str(task.coro)+res

async def cancel_tasks(tasks):
    for t in filter(lambda t: t and not t.done(), tasks):
        t.cancel()
async def cancel_gather_wait_for_ms(tasks, timeout_ms=1000):
    for t in filter(lambda t: t and not t.done(), tasks):
        t.cancel()
    await gather_wait_for_ms(tasks      = tasks, 
                             timeout_ms = timeout_ms)

async def gather_wait_for_ms(tasks, timeout_ms=1000):
    #gather CAN definitely wait forever and lockup. <<<<<<<<<<<<<
    #cancel one-by-one, gather's runtime error will abort entire gather
    #surround with wait_for to prevent lockup
    errs = []
        
    # pause in case we created a task just before calling this function
    await asyncio.sleep_ms(0)

    for t in filter(lambda t: t and not t.done(), tasks):
        try:
            # print('gathering',t,t.done())
            await asyncio.wait_for_ms(asyncio.gather(t, return_exceptions=True), timeout_ms)
            # print('gathered',t,t.done())
        except RuntimeError as err:
            # trap "RuntimeError: can't gather"
            # this is thrown if task is done.  Very hard to guarantee pure atomic behavior between 
            # checking for done and running gather. Micropython devs don't want to skip done tasks.
            # Being EXPLICIT with this is protection to make sure we never err out because gathering done task
            pass
        except asyncio.TimeoutError as err:
            if not t.done():
                errs.append((repr_task(t), err))
        except Exception as err:
            if not t.done():
                errs.append((repr_task(t), err))
    if errs:
        raise Exception('GATHER ERRS:'+str(errs))
