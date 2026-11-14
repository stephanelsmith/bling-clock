# Debug logging mixin, from titan-upyesp32s (upyesp32s/debug/__init__.py).
# Titan only prints when board.is_plugged(); the bling clock is always on USB,
# so that check is dropped. Use set_debug_silent(True) to turn output off.

import sys
import time
from micropython import const

# show time prefix?
_SHOW_TIME = const(0)

DEBUG_SILENT = False

def set_debug_silent(silent):
    global DEBUG_SILENT
    DEBUG_SILENT = silent

def _dbgprn(*args, **kwargs):
    if not DEBUG_SILENT:
        print(*args, **kwargs)

def _dbgprn_exception(err):
    if not DEBUG_SILENT:
        sys.print_exception(err)

def _log(name, *args):
    if DEBUG_SILENT:
        return
    if _SHOW_TIME:
        ms = time.ticks_ms()
        _dbgprn('{:7}.{:03}'.format(ms//1000, ms%1000), end='')
        _dbgprn(' | ',end='')
    _dbgprn(name,end='')
    for el in args:
        _dbgprn(' | ',end='')
        _dbgprn(el,end='')
    _dbgprn('')


class DebugMixin:
    def debug(self, *args):
        _log(self._name, *args)
    async def adebug(self, *args):
        _log(self._name, *args)
    def print_exception(self, err):
        if self._name:
            _dbgprn(self._name)
        _dbgprn_exception(err)
