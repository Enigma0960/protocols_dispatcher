import asyncio
import pytest
from protocols_dispatcher.dispatcher import (
    AbstractProtocol, AbstractTransport
)


class DummyProtocol(AbstractProtocol):
    def __init__(self):
        self.sent = []
        self.incoming = []

    async def matches(self, raw: bytes) -> bool:
        return True

    async def deserialize(self, data: bytes):
        pkt = {"raw": data}
        self.incoming.append(pkt)
        return [pkt]

    async def serialize(self, packet):
        self.sent.append(packet)
        return f"ENC({packet['raw'].hex()})".encode()


class DummyTransport(AbstractTransport):
    def __init__(self):
        super().__init__()
        self.outbox = []

    async def send(self, data: bytes):
        self.outbox.append(data)

    async def run(self):
        pass
