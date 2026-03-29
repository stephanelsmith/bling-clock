
import asyncio
import sys
from aiomqtt import Client, MqttError
import ssl
import zlib
import rich.progress

FW_PATH = '/home/ssmith/micropython/ports/esp32/build-BLING/micropython.bin' # the ota parition
OTA_BLOCK_SIZE = 4096

def int_div_ceil(total_size, chunk_size):
    return total_size//chunk_size + (1 if total_size%chunk_size else 0)

async def publish_async_message():
    # Use an asynchronous context manager to connect and disconnect automatically
    try:
        async with Client("broker.hivemq.com", 
                          port=8883,
                          tls_context=ssl.create_default_context(),
                          ) as client:
            page = 0
            with open(FW_PATH, 'rb') as f:
                f.seek(0, 2)
                fsz = f.tell()
                f.seek(0)
                num_pages = int_div_ceil(fsz, OTA_BLOCK_SIZE)
                print(fsz, OTA_BLOCK_SIZE, fsz/OTA_BLOCK_SIZE)
                for page in rich.progress.track(range(num_pages)):
                    p = f.read(OTA_BLOCK_SIZE)
                    # b = bytearray(OTA_BLOCK_SIZE)
                    # b[:len(p)] = p
                    z = zlib.compress(p)
                    print('PAGE:{}/{} {}-{}'.format(page, num_pages, len(p), len(z)))
                    await client.publish(f'ki5tof/ota/{page}', payload=z, qos=1)
                    # await client.publish(f'ki5tof/ota/{page}', payload=b, qos=1)
                    await asyncio.sleep(0.75)
            await asyncio.sleep(1)
            await client.publish(f'ki5tof/ota/done', payload=b'\x00', qos=1)

    except MqttError as error:
        print(f"An MQTT error occurred: {error}")

def main():
    # Run the asynchronous function using asyncio.run()
    asyncio.run(publish_async_message())

if __name__ == "__main__":
    main()

