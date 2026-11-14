import asyncio
import threading

from app.api.image_slots import Limiter, SlotScheduler


async def _never() -> bool:
    return False


def test_finish_from_thread_wakes_waiter():
    async def go():
        lim = Limiter("i", ceiling=1)
        lim.slots = 1
        held = await lim.acquire("focus", _never)
        waiter = asyncio.create_task(lim.acquire("focus", _never))
        await asyncio.sleep(0.05)
        assert not waiter.done()
        t = threading.Thread(target=held.finish, args=(200,))
        t.start()
        t.join()
        got = await asyncio.wait_for(waiter, 2)
        assert lim.in_flight == 1
        got.finish(200)
        await asyncio.sleep(0.05)
        assert lim.in_flight == 0

    asyncio.run(go())


def test_ceiling_read_is_cached():
    calls: list[str] = []

    def read(host_class: str) -> int | None:
        calls.append(host_class)
        return 3

    sched = SlotScheduler(read)
    for _ in range(5):
        sched.limiter("nhentai", "t")
    assert calls == ["t"]
    assert sched.limiter("nhentai", "t").ceiling == 3
