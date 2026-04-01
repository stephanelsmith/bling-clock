
import sys
import asyncio

from display import write_text

from lib.mytime import lcl_timetuple

# draw the clock into the framebuf as a mask
async def clock_coro(frmmsk):
    global is_nighttime
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

                await time_24hour(frmmsk = frmmsk)

            except asyncio.CancelledError:
                raise
            except Exception as err:
                sys.print_exception(err)
    except asyncio.CancelledError:
        raise
    except Exception as err:
        sys.print_exception(err)

async def time_24hour(frmmsk):
    yr, mth, day, hr, min, sec, msec, = lcl_timetuple()
    sep = ':' if sec%2==0 else ' '
    time = '{:02}{}{:02}'.format(hr,sep,min)
    hue = (min*60+sec)*360//(60*60)
    val = 1 if (hr < 8 or hr > 19) else 5
    write_text(frmmsk  = frmmsk,
               text    = time.encode(),
               )
