# Bling

TinyS3 is available through [UnexpectedMaker's store](https://unexpectedmaker.com/) directy, Mouser Digkey, Sparkfun and others. He's got tons of other great boards to check out to!

<p align="center">
  <img src="https://github.com/stephanelsmith/micro-wspr/blob/master/docs/s3/pins.jpg?raw=true" alt="" width="600"/>
</p>

## :hammer: Building Micropython Firware for TinyS3
#### Install pre-reqs
```
apt install cmake python3-libusb1
```
### ESP-IDF v5.5.1
#### Clone the Espressif ESP-IDF repo
```
git clone --depth 1 --branch v5.5.1 https://github.com/espressif/esp-idf.git esp-idf-v5.5.1
ln -sf esp-idf-v5.5.1 esp-idf
cd esp-idf
git submodule update --init --recursive
./install.sh
source export.sh
```
From here on, you will need to source ```export.sh``` to setup your environment.

#### Now clone the Micropython repo
```
git clone git@github.com:micropython/micropython.git micropython
cd micropython
git submodule update --init --recursive
make -C mpy-cross
cd ports/esp32
```
From here, the commands assume the current working directory is ```micropython/ports/esp32```.

#### Add the board file from the micro-wspr folder into the micropython build folder
```
ln -sf ~/micro-wspr/upy/boards/BLING boards/.
```

#### Build micropython port with C modules
```
make BOARD=BLING USER_C_MODULES=~/bling-clock/upy/c_modules/esp32.cmake
```


#### Flash the esp32 chip.
Before flashing the ESP32S3 needs to be in the bootloader.  This is done by holding the ```boot``` button and clicking ```reset```.  You can find the right comm port with ```py -m serial.tools.list_ports```.  You may need to ```py -m pip install pyserial``` first.
```
py -m esptool --chip esp32s3 --port COM4 write-flash -z 0 .\micropython\ports\esp32\build-BLING\firmware.bin
```


## :runner: Trying the TinyS3 Port
Fire up a terminal and connect to the device (use ```py -m serial.tools.list_ports``` to find the COM port)
```
py -m serial.tools.miniterm COM20
```


