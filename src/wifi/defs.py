
import collections

#if we are consistently not connecting, reboot
REBOOT_ON_FAILS    = const(1)
REBOOT_AFTER_FAILS = const(5)

AddrInfo = collections.namedtuple('AddrInfo',
    [
        'host',
        'port',
        'addrinfo',
    ]
)

# AP names are pre-fixes, essentially SSID.*
APs = [
    ('ThunderFace','sararocksmyworld'),
]
WIFI_TX_POWER = 18

