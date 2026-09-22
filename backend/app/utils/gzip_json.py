"""GZip только для JSON-ответов API.

Тело заметки (`content_json` со встроенными изображениями) доходит до мегабайтов,
и на таком тексте gzip экономит кратно больше, чем стоит его CPU. Бинарные
вложения сознательно не трогаем: они уже сжаты, а буферизация ломала бы
Range-запросы (перемотка аудио) и отдачу файлов потоком.
"""

import asyncio
import gzip

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Ответы мельче этого порога сжимать невыгодно: заголовки съедают выигрыш.
MIN_GZIP_SIZE = 1024
#: С этого размера сжимаем в отдельном потоке, чтобы не блокировать event loop.
OFFLOAD_SIZE = 256 * 1024
_GZIP_LEVEL = 6


def _compress(body: bytes) -> bytes:
    return gzip.compress(body, _GZIP_LEVEL)


class JsonGZipMiddleware:
    """Сжимает `application/json`, если клиент прислал `Accept-Encoding: gzip`."""

    def __init__(self, app: ASGIApp, minimum_size: int = MIN_GZIP_SIZE) -> None:
        self.app = app
        self.minimum_size = minimum_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        accept = Headers(scope=scope).get("accept-encoding", "")
        if "gzip" not in accept.lower():
            await self.app(scope, receive, send)
            return
        responder = _JsonGZipResponder(self.app, self.minimum_size)
        await responder(scope, receive, send)


class _JsonGZipResponder:
    def __init__(self, app: ASGIApp, minimum_size: int) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.send: Send | None = None
        self.start_message: Message | None = None
        self.body = bytearray()
        self.compressing = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        await self.app(scope, receive, self._send)

    async def _send(self, message: Message) -> None:
        assert self.send is not None
        if message["type"] == "http.response.start":
            headers = Headers(raw=message["headers"])
            content_type = headers.get("content-type", "")
            self.compressing = content_type.startswith(
                "application/json"
            ) and "content-encoding" not in headers
            if not self.compressing:
                await self.send(message)
                return
            self.start_message = message
            return

        if message["type"] != "http.response.body" or not self.compressing:
            await self.send(message)
            return

        self.body.extend(message.get("body", b""))
        if message.get("more_body", False):
            return

        start = self.start_message
        assert start is not None
        body = bytes(self.body)
        if len(body) >= self.minimum_size:
            body = (
                await asyncio.to_thread(_compress, body)
                if len(body) >= OFFLOAD_SIZE
                else _compress(body)
            )
            headers = MutableHeaders(raw=start["headers"])
            headers["Content-Encoding"] = "gzip"
            headers["Content-Length"] = str(len(body))
            vary = headers.get("Vary")
            headers["Vary"] = f"{vary}, Accept-Encoding" if vary else "Accept-Encoding"
        await self.send(start)
        await self.send({"type": "http.response.body", "body": body, "more_body": False})
