import pytest

from src.protocols_dispatcher.dispatcher import Dispatcher, ProtocolRouter

from .helpers import *


class TestDispatcher(object):
    def test_create_dispatcher(self, protocol, transport):
        dispatcher = Dispatcher(protocol=protocol, transport=transport)

        assert dispatcher is not None
        assert dispatcher.transport is transport
        assert dispatcher.protocol is protocol

    @pytest.mark.asyncio
    async def test_process_dispatch(self, protocol, transport):
        dispatcher = Dispatcher(protocol=protocol, transport=transport)

        result = await dispatcher.process(b'')
        assert result is not None
        assert len(result) == 1
        assert result[0]['raw'] == b''

        result = await dispatcher.process(b'test')
        assert result is not None
        assert len(result) == 1
        assert result[0]['raw'] == b'test'


class TestProtocolRouter(object):
    def test_protocol_router(self, protocol, transport):
        router = ProtocolRouter(protocols={protocol: transport})
        assert router is not None
