
import collections

AddrInfo = collections.namedtuple('AddrInfo',
    [
        'host',
        'port',
        'addrinfo',
    ]
)

# AP names are pre-fixes, essentially SSID.*
APs = [
    ('Thunderface','sararocksmyworld'),
]
WIFI_TX_POWER = 10

