import asyncio

from vf_core.render_strategies import PeriodicRenderStrategy, QueuedRenderStrategy


async def test_periodic_coalesces_multiple_requests():
    calls = 0

    async def render():
        nonlocal calls
        calls += 1

    strat = PeriodicRenderStrategy(render, min_interval=0.1)
    await strat.start()
    try:
        # Several synchronous requests arrive before the loop renders once.
        for _ in range(5):
            strat.request_render()
        await asyncio.sleep(0.05)  # still within the first interval
        assert calls == 1  # coalesced into a single render
    finally:
        await strat.stop()


async def test_periodic_renders_again_after_interval():
    calls = 0

    async def render():
        nonlocal calls
        calls += 1

    strat = PeriodicRenderStrategy(render, min_interval=0.1)
    await strat.start()
    try:
        strat.request_render()
        await asyncio.sleep(0.05)
        assert calls == 1

        strat.request_render()
        await asyncio.sleep(0.2)  # past the interval
        assert calls == 2
    finally:
        await strat.stop()


async def test_queued_processes_each_request_in_order():
    rendered = []

    async def render(data):
        rendered.append(data)

    strat = QueuedRenderStrategy(render, min_interval=0)
    await strat.start()
    try:
        for i in range(3):
            strat.request_render(i)
        await asyncio.sleep(0.1)
        assert rendered == [0, 1, 2]
    finally:
        await strat.stop()


async def test_queued_drops_oldest_when_full():
    rendered = []

    async def render(data):
        rendered.append(data)

    strat = QueuedRenderStrategy(render, min_interval=0)
    # Fill beyond the queue maxsize (20) before the loop starts consuming.
    for i in range(25):
        strat.request_render(i)

    await strat.start()
    try:
        await asyncio.sleep(0.1)
        # The oldest 5 are dropped, the most recent 20 survive in order.
        assert rendered == list(range(5, 25))
    finally:
        await strat.stop()
