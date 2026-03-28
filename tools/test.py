
import asyncio
import sys
from aiomqtt import Client, MqttError
import ssl
import zlib

# Note: For Windows, uncomment the following lines to use the correct event loop
# if sys.platform.lower() == "win32" or os.name.lower() == "nt":
#     from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
#     set_event_loop_policy(WindowsSelectorEventLoopPolicy())

async def publish_async_message():
    # Use an asynchronous context manager to connect and disconnect automatically
    try:
        async with Client("broker.hivemq.com", 
                          port=8883,
                          tls_context=ssl.create_default_context(),
                          ) as client:
            topic = "ki5tof/test"
            p = bytes(range(10))
            z = zlib.compress(p)
            print(z)

            # The publish method is an awaitable coroutine
            await client.publish(topic, payload=z, qos=1)

    except MqttError as error:
        print(f"An MQTT error occurred: {error}")

def main():
    # Run the asynchronous function using asyncio.run()
    asyncio.run(publish_async_message())

if __name__ == "__main__":
    main()

