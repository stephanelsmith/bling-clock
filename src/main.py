
# from callen import main
# main()

import time
import machine

from ss import main

def bootloader():
    # RTC_CNTL_OPTION1_REG address for ESP32-S3
    # Setting the bit to force download boot
    RTC_CNTL_OPTION1_REG = 0x60008000 + 0x128
    RTC_CNTL_FORCE_DOWNLOAD_BOOT = 1 << 0
    
    print("Rebooting into Bootloader mode...")
    time.sleep(0.5)
    
    # Write the flag to RTC memory (survives soft reset)
    machine.mem32[RTC_CNTL_OPTION1_REG] |= RTC_CNTL_FORCE_DOWNLOAD_BOOT
    
    # Trigger a reset
    # machine.reset()
    machine.deepsleep(1)

main()

