from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass

from typing import List, Dict, Any, Sequence, Callable, Optional, Type


class AbstractProtocol:

    async def serialize(self, packet: Dict[str, Any]) -> bytes | None:  # noqa: D401
        """
        Преобразует «высокоуровневый» пакет в байтовую последовательность.

        :param packet: Словарь с полями пакета; структуру задаёт реализация
                       конкретного протокола.
        :type  packet: dict[str, Any]
        :return: Готовый набор байтов **или** ``None``, если передавать
                 наружу ничего не нужно (например, внутренний keep-alive).
        :rtype: bytes | None
        """

    async def deserialize(self, data) -> List[Dict[str, Any]]:  # noqa: D401
        """
        Разбирает входящий поток данных в один или несколько пакетов.

        Метод вызывается каждый раз, когда транспорт получает очередной
        блок raw-байтов. Реализация должна самостоятельно буферизовать
        неполные сообщения и возвращать их только после полной сборки.

        :param data: Сырые данные из транспорта. Может содержать
                     как целые, так и неполные сообщения.
        :type  data: bytes
        :return: Список полностью разобранных пакетов;
                 может быть пустым, если данных мало.
        :rtype: list[dict[str, Any]]
        """

    async def matches(self, raw: bytes) -> bool:  # noqa: D401
        """
        Быстрая проверка, относится ли входящий фрейм к данному протоколу.

        Используется роутером, чтобы решить, какой протокол
        должен обработать полученный набор байтов, не выполняя при этом
        полноценную десериализацию.

        :param raw: Фрагмент входящих байт (обычно первые N байтов кадра).
        :type  raw: bytes
        :return: ``True``, если кадр узнаётся, иначе ``False``.
        :rtype: bool
        """
        return True


class AbstractFilter:
    def __call__(self, packet: Dict[str, Any], raw: bytes) -> bool:
        return self.matches(packet, raw)

    def matches(self, packet: Dict[str, Any], raw: bytes) -> bool:  # noqa: D401
        """
        Проверяет, удовлетворяет ли пакет заданному фильтру.

        :param packet: Разобранный словарь, полученный из
                       :py:meth:`AbstractProtocol.deserialize`.
        :type  packet: dict[str, Any]
        :param raw: Оригинальная сырья байтов пакета, как она пришла
                    от транспорта.
        :type  raw: bytes
        :return: ``True``, если пакет проходит фильтр, иначе ``False``.
        :rtype: bool
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"


class AbstractTransport():
    def __init__(self):
        self.dispatcher: Optional['Dispatcher'] = None

    async def send(self, data: bytes) -> None:  # noqa: D401
        """
        Отправляет закодированный набор байтов через конкретный транспорт.

        Реализация должна гарантировать, что *весь* буфер
        поставлен в очередь на передачу до возврата управления
        (см. пример с `SerialTransport.send`) :contentReference[oaicite:1]{index=1}.

        :param data: Готовый кадр, возвращённый
                     :py:meth:`AbstractProtocol.serialize`.
        :type  data: bytes
        :return: Ничего. Короутина завершается, когда данные
                 приняты транспортом.
        :rtype: None
        """

    async def run(self) -> None:  # noqa: D401
        """
        Запускает цикл приёма данных у транспорта.

        Короутина должна непрерывно считывать входящие байты,
        передавать их в :pyattr:`dispatcher.process <Dispatcher.process>`
        и завершаться только при закрытии/остановке транспорта.
        Типичный пример реализации — см. `SerialTransport.run`
        :contentReference[oaicite:2]{index=2}.

        :return: Ничего. Короутина работает до отмены
                 либо естественного завершения.
        :rtype: None
        """


class AnyFilter(AbstractFilter):
    def matches(self, packet: Dict[str, Any], raw: bytes) -> bool:
        return True


class Dispatcher:
    def __init__(self, protocol: AbstractProtocol, transport: AbstractTransport):
        if not isinstance(protocol, AbstractProtocol):
            raise TypeError("protocol must be subclass of AbstractProtocol")
        if not isinstance(transport, AbstractTransport):
            raise TypeError("transport must be subclass of AbstractTransport")

        self._protocol = protocol
        self._transport = transport
        self._transport.dispatcher = self
        self._handlers: List[tuple[Sequence[AbstractFilter], Callable[[Dict[str, Any]], Any | None]]] = []

    @property
    def protocol(self) -> AbstractProtocol:
        return self._protocol

    @property
    def transport(self) -> AbstractTransport:
        return self._transport

    def handler(self, *filters: AbstractFilter):
        def decorator(fn: Callable[[Dict[str, Any]], Any | None]):
            self._handlers.append((filters, fn))
            return fn

        return decorator

    def add_callback(self, *filters: AbstractFilter, fn: Callable[[Dict[str, Any]], Any]):
        self._handlers.append((filters, fn))

    async def process(self, raw: bytes) -> List[Dict[str, Any]] | None:
        if not await self._protocol.matches(raw):
            return None

        packets = await self._protocol.deserialize(raw)
        for packet in packets:
            for filt_seq, fn in self._handlers:
                if all(check(packet, raw) for check in filt_seq):
                    res = await fn(packet) if inspect.iscoroutinefunction(fn) else fn(packet)
                    if res is not None:
                        await self.send(res)

        return packets

    async def send(self, packet: Dict[str, Any]):
        data = await self._protocol.serialize(packet)
        if data is not None:
            print(f"Sending: {data.hex() if isinstance(data, (bytes, bytearray)) else data}")
            await self._transport.send(data)


@dataclass
class RouterInfo:
    transport: AbstractTransport
    protocol: AbstractProtocol
    dispatcher: Dispatcher


class ProtocolRouter:
    def __init__(
            self,
            *,
            dispatchers: Optional[List[Dispatcher]] = None,
            protocols: Optional[Dict[AbstractProtocol, AbstractTransport]] = None
    ):
        self._routing: List[RouterInfo] = []

        if not dispatchers and not protocols:
            raise ValueError("At least one dispatcher and protocol must be specified")

        if dispatchers is not None:
            for dispatcher in dispatchers:
                info = RouterInfo(dispatcher.transport, dispatcher.protocol, dispatcher)
                self._routing.append(info)

        if protocols is not None:
            for protocol, transport in protocols.items():
                dispatcher = Dispatcher(protocol, transport)
                info = RouterInfo(dispatcher.transport, dispatcher.protocol, dispatcher)
                self._routing.append(info)

    @property
    def protocols(self) -> List[AbstractProtocol]:
        return [info.protocol for info in self._routing]

    @property
    def transports(self) -> List[AbstractTransport]:
        return [info.transport for info in self._routing]

    @property
    def dispatchers(self) -> List[Dispatcher]:
        return [info.dispatcher for info in self._routing]

    @property
    def routing(self) -> List[RouterInfo]:
        return self._routing

    def rout(self, protocol: AbstractProtocol) -> Optional[RouterInfo]:
        for info in self._routing:
            if info.protocol == protocol:
                return info
        return None

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
                raise TypeError("Filter must be PacketFilter instance or subclass")

        # select protocols
        if protocol is None:
            selected = [self._routing[0].protocol]
        elif isinstance(protocol, AbstractProtocol):
            selected = [protocol]
        elif inspect.isclass(protocol) and issubclass(protocol, AbstractProtocol):
            selected = [p for p in self._routing if isinstance(p, protocol)]
        else:
            raise TypeError("Protocol must be AbstractProtocol instance or subclass")

        if not selected:
            raise KeyError("Specified protocol is not registered in router")

        def decorator(fn: Callable[[Dict[str, Any]], Any | None]):
            for proto in selected:
                rout = self.rout(proto)
                if rout is not None:
                    rout.dispatcher.handler(*filters)(fn)
            return fn

        return decorator

    async def process(self, protocol: AbstractProtocol, raw: bytes) -> Dict[str, Any] | None:
        rout = self.rout(protocol)
        if rout is None:
            return None

        return await rout.dispatcher.process(raw)

    async def send(self, protocol: AbstractProtocol, packet: Dict[str, Any]):
        rout = self.rout(protocol)
        if rout is None:
            return
        await rout.dispatcher.send(packet)
