"""Relay an upstream body to the client and close the upstream when the client aborts."""

from collections.abc import AsyncGenerator, Callable, Iterator

from starlette.concurrency import run_in_threadpool

# One thread hop per chunk: big enough to keep a video flowing, small enough to stop soon.
CHUNK_SIZE = 128 * 1024


async def relay(chunks: Iterator[bytes], close: Callable[[], None]) -> AsyncGenerator[bytes, None]:
    """Yield chunks from a sync iterator; `close` runs on end, error and client abort.

    A seek makes the browser drop its open request. Starlette cancels the body task then and
    runs no background task, so the upstream connection would stay open until garbage collection.
    """
    try:
        while True:
            chunk = await run_in_threadpool(next, chunks, None)
            if chunk is None:
                return
            yield chunk
    finally:
        closer = getattr(chunks, "close", None)
        if closer is not None:
            closer()
        close()
