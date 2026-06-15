import asyncio

from vf_core.message_bus import MessageBus


async def _collect(bus, topic, n, out):
    """Subscribe and append the first x messages into "out", then stop."""
    async for msg in bus.subscribe(topic):
        out.append(msg)
        if len(out) >= n:
            break


async def test_publish_delivers_to_subscriber():
    bus = MessageBus()
    received = []
    task = asyncio.create_task(_collect(bus, "ais.raw", 1, received))
    await asyncio.sleep(0.05)  # let the subscription register

    await bus.publish("ais.raw", "!AIVDM,1,1,,B,13P;lhP005wj=OrNShTenrj80@3Q,0*28")

    await asyncio.wait_for(task, timeout=1)
    assert received == ["!AIVDM,1,1,,B,13P;lhP005wj=OrNShTenrj80@3Q,0*28"]


async def test_publish_reaches_all_subscribers():
    bus = MessageBus()
    a, b = [], []
    ta = asyncio.create_task(_collect(bus, "t", 1, a))
    tb = asyncio.create_task(_collect(bus, "t", 1, b))
    await asyncio.sleep(0.05)

    await bus.publish("t", 210)

    await asyncio.wait_for(asyncio.gather(ta, tb), timeout=1)
    assert a == [210]
    assert b == [210]


async def test_publish_without_subscribers_is_noop():
    bus = MessageBus()
    await bus.publish("nobody", "x")  # must not raise


async def test_subscriber_only_receives_its_topic():
    bus = MessageBus()
    received = []
    task = asyncio.create_task(_collect(bus, "wanted", 1, received))
    await asyncio.sleep(0.05)

    await bus.publish("other", "ignored")
    await bus.publish("wanted", "kept")

    await asyncio.wait_for(task, timeout=1)
    assert received == ["kept"]


async def test_messages_preserve_publish_order():
    bus = MessageBus()
    received = []
    task = asyncio.create_task(_collect(bus, "t", 3, received))
    await asyncio.sleep(0.05)

    for i in range(3):
        await bus.publish("t", i)

    await asyncio.wait_for(task, timeout=1)
    assert received == [0, 1, 2]


async def test_shutdown_stops_subscribers():
    bus = MessageBus()
    received = []

    async def consume():
        async for msg in bus.subscribe("t"):
            received.append(msg)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)

    await bus.shutdown()

    # The shutdown sentinel should end the receive loop cleanly.
    await asyncio.wait_for(task, timeout=1)
    assert received == []
