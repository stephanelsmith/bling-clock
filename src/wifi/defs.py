
import board
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
if board.BRD == b'BLING':
    APs = [
        ('ATTsTtW222','p2kydzyekv9h'),
        ('ThunderFace2','sararocksmyworld'),
        ('1314','1314Puma!'),
    ]
    WIFI_TX_POWER = 18
else:
    APs = [
        ('ATTsTtW222','p2kydzyekv9h'),
    ]

    if board.REVISION in [0,1]:
        # s3 compatibilty
        WIFI_TX_POWER     = 6 #dBm
    else:
        WIFI_TX_POWER     = 20 #dBm

