
import sys
import asyncio
import micropython
from font import char_to_pixels

NEOPIXELS_LEN = const(320)
NEOPIXELS_ROW = const(40)
_NEOPIXELS_MAX_CHARS = const(5)


# hue
LED_HUE_RED       = const(0)
LED_HUE_REDORA    = const(5)
LED_HUE_ORANGE    = const(20)
LED_HUE_YELLOW    = const(45)
LED_HUE_GREEN     = const(85)
LED_HUE_TEAL      = const(130)
LED_HUE_LIGHTBLUE = const(160)
LED_HUE_BLUE      = const(165)
LED_HUE_DARKBLUE  = const(170)
LED_HUE_PUPLE     = const(175)
LED_HUE_PINK      = const(220)

# 0,0 top left
@micropython.viper
def xy_to_i(x:int, y:int) -> int:
    return x+y*NEOPIXELS_ROW
@micropython.viper
def i_to_xy(i:int):
    return (i % NEOPIXELS_ROW, i // NEOPIXELS_ROW)

@micropython.native
def write_text(frmmsk, text:bytes, jright=True, hue=LED_HUE_LIGHTBLUE, val=5):
    j = max(_NEOPIXELS_MAX_CHARS-len(text),0)
    if jright:
        text = b' '*j+text
    else:
        text = text + b' '*j
    for i in range(NEOPIXELS_LEN):
        frmmsk[i] = 0
    for i,c in enumerate(text[:_NEOPIXELS_MAX_CHARS]):
        ps = char_to_pixels(c) # get character
        for x,p in enumerate(ps): # for each column
            for y in range(8): # for each row
                v = val if p&(0x01<<y) else 0
                # neo[xy_to_i(i*8+x, y)] = hsv_to_rgb(hue, 255, v)
                frmmsk[xy_to_i(i*8+x, y)] = 1 if p&(0x01<<y) else 0

@micropython.viper
def hsv_to_rgb(h:int, s:int, v:int):
    #adapted from c example
    h %= 256
    s %= 256
    v %= 256
    reg:int = h // 43 #region  255/6
    rem:int = (h - (reg * 43)) * 6 #remainder
    p:int = (v * (255 - s)) >> 8
    q:int = (v * (255 - ((s * rem) >> 8))) >> 8
    t:int = (v * (255 - ((s * (255 - rem)) >> 8))) >> 8
    if reg == 0:
        return (v, t, p)
    if reg == 1:
        return (q, v, p)
    if reg == 2:
        return (p, v, t)
    if reg == 3:
        return (p, q, v)
    if reg == 4:
        return (t, p, v)
    if reg == 5:
        return (v, p, q)


# Build a 256-entry hue -> color table, in the strip's byte order (G,R,B).
# Saturation/value are constant, so color depends only on hue.
# Call once at startup (per brightness); pass the result to render().
def make_palette(val=5, sat=255):
    pal = bytearray(256*3)
    for h in range(256):
        r, g, b = hsv_to_rgb(h, sat, val)
        pal[h*3]   = g
        pal[h*3+1] = r
        pal[h*3+2] = b
    return pal

_NEOPIXELS_COL = const(NEOPIXELS_LEN // NEOPIXELS_ROW)

# Fill neopixel buffer (neo.buf, GRB) from the mask + palette. No allocation.
# Rainbow runs along x; hue_off (0..255) scrolls it.
@micropython.viper
def render(buf, mask, pal, hue_off:int):
    b = ptr8(buf)
    m = ptr8(mask)
    p = ptr8(pal)
    i:int = 0
    for y in range(_NEOPIXELS_COL):
        for x in range(NEOPIXELS_ROW):
            o:int = i*3
            if m[i]:
                h:int = (((x*256)//NEOPIXELS_ROW) - hue_off) & 255
                h3:int = h*3
                b[o]   = p[h3]
                b[o+1] = p[h3+1]
                b[o+2] = p[h3+2]
            else:
                b[o]   = 0
                b[o+1] = 0
                b[o+2] = 0
            i += 1

# Same, but every lit pixel is one color: hue (0..255) looked up in pal.
@micropython.viper
def render_solid(buf, mask, pal, hue:int):
    b = ptr8(buf)
    m = ptr8(mask)
    p = ptr8(pal)
    h3:int = (hue & 255)*3
    g:int = p[h3]
    r:int = p[h3+1]
    bl:int = p[h3+2]
    for i in range(NEOPIXELS_LEN):
        o:int = i*3
        if m[i]:
            b[o]   = g
            b[o+1] = r
            b[o+2] = bl
        else:
            b[o]   = 0
            b[o+1] = 0
            b[o+2] = 0
