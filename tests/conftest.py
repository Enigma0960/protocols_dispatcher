import asyncio
import pytest

from protocols_dispatcher.dispatcher import Dispatcher

from tests.helpers import DummyProtocol, DummyTransport


@pytest.fixture
def proto():
    return DummyProtocol()


@pytest.fixture
def transport():
    return DummyTransport()


@pytest.fixture
def dispatcher(proto, transport):
    return Dispatcher(proto, transport)


# Делает pytest-asyncio совместимым с src-layout
@pytest.fixture(scope="session")
def event_loop_policy():
    policy = asyncio.get_event_loop_policy()
    return policy
