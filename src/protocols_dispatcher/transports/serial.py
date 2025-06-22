import asyncio
import aioserial

from ..dispatcher import AbstractTransport

_MAX_CHUNK_SIZE = 4096


class SerialTransport(AbstractTransport):
    def __init__(self, port: str, baudrate: int = 9600):
        super().__init__()

        self._stop_event = asyncio.Event()

        self._port = port
        self._baudrate = baudrate

        self._serial: aioserial.AioSerial = aioserial.AioSerial(
            self._port,
            self._baudrate,
            timeout=0,
        )

    @property
    def port(self):
        return self._port

    @property
    def baudrate(self):
        return self._baudrate

    async def send(self, data: bytes) -> None:
        if not self._serial.is_open:
            return
        await self._serial.write_async(data)

    async def run(self) -> None:
        while not self._stop_event.is_set():
            if not self._serial.is_open:
                raise RuntimeError('Serial port is not open')

            if self._serial.in_waiting:
                data: bytes = await self._serial.read_async(min(self._serial.in_waiting, _MAX_CHUNK_SIZE))
                await self.dispatcher.process(data)
            await asyncio.sleep(0)

    def stop(self):
        self._stop_event.set()
