import asyncio
from typing import override

import pytest

from src.protocols_dispatcher.dispatcher import (
    AbstractProtocol, AbstractTransport
)


class DummyProtocol(AbstractProtocol):
    def __init__(self):
        self.sent = []
        self.incoming = []

    @override
    async def matches(self, raw: bytes) -> bool:
        return True

    @override
    async def deserialize(self, data: bytes):
        pkt = {"raw": data}
        self.incoming.append(pkt)
        return [pkt]

    @override
    async def serialize(self, packet):
        self.sent.append(packet)
        return f"ENC({packet['raw'].hex()})".encode()


class DummyTransport(AbstractTransport):
    def __init__(self):
        super().__init__()
        self.outbox = []

    @override
    async def send(self, data: bytes):
        self.outbox.append(data)

    @override
    async def run(self):
        pass
