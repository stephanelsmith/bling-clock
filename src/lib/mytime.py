# Local time helpers for the bling clock.
#
# lib.ntptime.settime() sets the RTC to UTC; this module converts that to local
# time. Modeled on RTC.lcl_timetuple() in titan-upyesp32s (rtc/rtc.py), but as
# plain functions with the timezone (and US daylight saving) built in.

import time
from micropython import const

# US Central: CST is UTC-6, CDT is UTC-5. Change these for another timezone;
# set USE_DST = False for a fixed offset.
TZ_STD_S = const(-6 * 3600)
TZ_DST_S = const(-5 * 3600)
USE_DST = True

# cache of (year, dst_start_utc, dst_end_utc), recomputed when the year changes.
# lcl_timetuple() is called every few ms from display_coro, so keep it cheap.
_dst_cache = (0, 0, 0)

def _nth_sunday_utc(yr, mth, nth, hr_utc):
    # seconds since epoch (UTC) of the nth Sunday of yr/mth at hr_utc:00 UTC
    wd = time.gmtime(time.mktime((yr, mth, 1, 0, 0, 0, 0, 0)))[6]  # Mon=0 .. Sun=6
    day = 1 + (6 - wd) % 7 + (nth - 1) * 7
    return time.mktime((yr, mth, day, hr_utc, 0, 0, 0, 0))

def _dst_bounds(yr):
    global _dst_cache
    if _dst_cache[0] != yr:
        # US rules: 2nd Sunday of March 02:00 local standard time,
        #           to 1st Sunday of November 02:00 local daylight time
        start = _nth_sunday_utc(yr, 3,  2, 2 - TZ_STD_S // 3600)
        end   = _nth_sunday_utc(yr, 11, 1, 2 - TZ_DST_S // 3600)
        _dst_cache = (yr, start, end)
    return _dst_cache

def tz_s(utc_s=None):
    # current UTC offset in seconds
    if not USE_DST:
        return TZ_STD_S
    if utc_s is None:
        utc_s = time.time()
    yr, start, end = _dst_bounds(time.gmtime(utc_s)[0])
    return TZ_DST_S if start <= utc_s < end else TZ_STD_S

def utc_timetuple():
    #       year    month   day     hour    minute  sec     msec
    t_ms = time.time_ns() // 1_000_000
    tup = time.gmtime(t_ms // 1000)
    return (tup[0], tup[1], tup[2], tup[3], tup[4], tup[5], t_ms % 1000)

def lcl_timetuple():
    #       year    month   day     hour    minute  sec     msec
    t_ms = time.time_ns() // 1_000_000
    utc_s = t_ms // 1000
    tup = time.gmtime(utc_s + tz_s(utc_s))
    return (tup[0], tup[1], tup[2], tup[3], tup[4], tup[5], t_ms % 1000)
