
import upydash as _ 
import asyncio
from primitives.queue import Queue, QueueEmpty, QueueFull

class PriorityQueue(Queue):
    def __init__(self, maxsize=0, maxlen=0):
        super().__init__(maxsize = maxsize)
        self._p_queue = []
        self._maxlen = maxlen  # >0: over the limit, drop oldest instead of blocking
        self.drops = 0

    def _get_priority(self):
        self._evget.set()  # Schedule all tasks waiting on get
        self._evget.clear()
        if len(self._p_queue) > 0:
            return (self._p_queue.pop(0), True)
        else:
            return (self._queue.pop(0), False)

    def _get(self):
        self._evget.set()  # Schedule all tasks waiting on get
        self._evget.clear()
        if len(self._p_queue) > 0 :
            return self._p_queue.pop(0)
        else:
            return self._queue.pop(0)

    async def get_priority(self):  #  Usage: item = await queue.get()
        while self.empty():  # May be multiple tasks waiting on get()
            # Queue is empty, suspend task until a put occurs
            # 1st of N tasks gets, the rest loop again
            await self._evput.wait()
        return self._get_priority()

    def get_priority_nowait(self):  # Remove and return an item from the queue.
        # Return an item if one is immediately available, else raise QueueEmpty.
        if self.empty():
            raise QueueEmpty()
        return self._get_priority()

    #ssmith, get the size of the next item, so we know what we are dealing with
    #before getting
    def peek_len(self):
        if self.empty():
            # raise error to differentiate length 0 from empty
            # raise QueueEmpty()
            # Return None instead, more friendly to caller
            return None
        if len(self._p_queue) > 0 :
            return len(self._p_queue[0])
        else:
            return len(self._queue[0])

    def _put(self, val, is_priority=False):
        self._evput.set()  # Schedule tasks waiting on put
        self._evput.clear()
        if is_priority:
            self._p_queue.append(val)
        else:
            self._queue.append(val)
        if self._maxlen and self.qsize() > self._maxlen:
            # drop oldest normal item first; priority only when there are no normal items
            (self._queue if self._queue else self._p_queue).pop(0)
            self.drops += 1

    def _prepend(self, val):
        self._evput.set()  # Schedule tasks waiting on put
        self._evput.clear()
        self._queue.insert(0,val)

    async def put(self, val, is_priority=False):  # Usage: await queue.put(item)
        while self.full():
            # Queue full
            await self._evget.wait()
            # Task(s) waiting to get from queue, schedule first Task
        self._put(val, is_priority)

    def put_nowait(self, val, is_priority=False):  # Put an item into the queue without blocking.
        if self.full():
            raise QueueFull()
        self._put(val, is_priority)

    def qsize(self):  
        # Number of items in the queue.
        return len(self._queue) + len(self._p_queue)

    def empty(self):  
        # Return True if the queue is empty, False otherwise.
        return self.qsize() == 0

    def clear(self):
        self._queue.clear()
        self._p_queue.clear()

