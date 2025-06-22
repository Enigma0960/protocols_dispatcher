from __future__ import annotations

import inspect

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Sequence, Callable, Optional


class AbstractProtocol(ABC):
    @abstractmethod
    async def serialize(self, packet: Dict[str, Any]) -> bytes | None:  # noqa: D401
        """"""

    @abstractmethod
    async def deserialize(self, data) -> List[Dict[str, Any]]:  # noqa: D401
        """"""

    @abstractmethod
    async def matches(self, raw: bytes) -> bool:  # noqa: D401
        """"""
        return True


class AbstractFilter(ABC):
    def __call__(self, packet: Dict[str, Any], raw: bytes) -> bool:
        return self.matches(packet, raw)

    @abstractmethod
    def matches(self, packet: Dict[str, Any], raw: bytes) -> bool:  # noqa: D401
        """"""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"


class AbstractTransport(ABC):
    def __init__(self):
        self.dispatcher: Optional['Dispatcher'] = None

    @abstractmethod
    async def send(self, data: bytes) -> None:  # noqa: D401
        """"""

    @abstractmethod
    async def run(self) -> None:  # noqa: D401
        """"""


class AnyFilter(AbstractFilter):
    def matches(self, packet: Dict[str, Any], raw: bytes) -> bool:
        return True


class Dispatcher:
    def __init__(self, protocol: AbstractProtocol, transport: AbstractTransport):
        self._protocol = protocol
        self._transport = transport
        self._handlers: List[tuple[Sequence[AbstractFilter], Callable[[Dict[str, Any]], Any | None]]] = []

    def handler(self, *filters: AbstractFilter):
        def decorator(fn: Callable[[Dict[str, Any]], Any | None]):
            self._handlers.append((filters, fn))
            return fn

        return decorator

    def add_callback(self, *filters: AbstractFilter, fn: Callable[[Dict[str, Any]], Any]):
        self._handlers.append((filters, fn))

    async def process(self, raw: bytes) -> Dict[str, Any] | None:
        if not await self._protocol.matches(raw):
            return None

        packets = await self._protocol.deserialize(raw)
        for packet in packets:
            for filt_seq, fn in self._handlers:
                if all(check(packet, raw) for check in filt_seq):
                    res = await fn(packet) if inspect.iscoroutinefunction(fn) else fn(packet)
                    if res is not None:
                        await self.send(res)

        return None

    async def send(self, packet: Dict[str, Any]):
        data = await self._protocol.serialize(packet)
        if data is not None:
            print(f"Sending: {data.hex() if isinstance(data, (bytes, bytearray)) else data}")
            await self._transport.send(data)


class ProtocolRouter:
    def __init__(self, protocols: Dict[AbstractProtocol, AbstractTransport]):
        self._dispatchers: Dict[AbstractProtocol, Dispatcher] = {}

        if not protocols:
            raise ValueError("At least one protocol must be provided")

        for protocol, transport in protocols.items():
            dispatcher = Dispatcher(protocol, transport)
            transport.dispatcher = dispatcher
            self._dispatchers[protocol] = dispatcher

        self._active: set[AbstractProtocol] = set(protocols.keys())
        self._single_proto: AbstractProtocol | None = next(iter(protocols.keys())) if len(protocols) == 1 else None

    def handler(
            self,
            *,
            protocol: AbstractProtocol | type[AbstractProtocol] | None = None,
            filter: AbstractFilter | type[AbstractFilter] | None = None,
    ):
        if filter is None:
            filters: tuple[AbstractFilter, ...] = ()
        else:
            if isinstance(filter, AbstractFilter):
                filters = (filter,)
            elif inspect.isclass(filter) and issubclass(filter, AbstractFilter):
                filters = (filter(),)
            else:
                raise TypeError("filter must be PacketFilter instance or subclass")

        # select protocols
        if protocol is None:
            if self._single_proto is not None:
                selected = [self._single_proto]
            else:
                selected = list(self._dispatchers.keys())
        elif isinstance(protocol, AbstractProtocol):
            selected = [protocol]
        elif inspect.isclass(protocol) and issubclass(protocol, AbstractProtocol):
            selected = [p for p in self._dispatchers if isinstance(p, protocol)]
        else:
            raise TypeError("protocol must be AbstractProtocol instance or subclass")

        if not selected:
            raise KeyError("Specified protocol is not registered in router")

        # decorator applying to chosen dispatchers
        def decorator(fn: Callable[[Dict[str, Any]], Any | None]):
            for proto in selected:
                self._dispatchers[proto].handler(*filters)(fn)
            return fn

        return decorator

    def dispatcher(self, proto: AbstractProtocol) -> Dispatcher:
        return self._dispatchers[proto]

    def activate_only(self, *protocols: AbstractProtocol):
        unknown = set(protocols) - self._dispatchers.keys()
        if unknown:
            raise KeyError(f"Unknown protocols: {unknown}")
        self._active = set(protocols)

    def activate_all(self):
        self._active = set(self._dispatchers)

    # ---------------- processing ----------------
    async def process(self, raw: bytes) -> Dict[str, Any] | None:
        if self._single_proto is not None and self._single_proto in self._active:
            # Fast path: only one protocol in whole router ⇒ no loop, minimal checks
            return await self._dispatchers[self._single_proto].process(raw)

        for proto in self._active:
            rsp = await self._dispatchers[proto].process(raw)
            if rsp is not None:
                return rsp

        return None

    async def send(self, proto: AbstractProtocol, packet: Dict[str, Any]):
        await self._dispatchers[proto].send(packet)
