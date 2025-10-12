from __future__ import annotations
import asyncio
import random
from typing import Any
from contextlib import suppress
from vf_core.message_bus import MessageBus
from vf_core.plugin_types import Plugin

DEFAULT_MESSAGES = [
    "!AIVDM,1,1,,B,13P;lhP005wj=OrNShTenrj80@3Q,0*28",
    "!AIVDM,1,1,,B,13M@DR@000Oj?=vNT`8H@K8J0@7O,0*66",
    "!AIVDM,1,1,,A,13P;lhP004wj=OtNShW01JnL0<13,0*71",
    "!AIVDM,1,1,,A,13P8fQhP11wjADlNSg@chOvR200m,0*32",
    "!AIVDM,1,1,,B,33P;lhP004wj=P4NShbP=bjh00=C,0*0E",
    "!AIVDM,2,1,3,B,53P;lh`2;:IS8=1?P01H:1<4p@tp00000000000l1p?664pB0=832EQD,0*50",
    "!AIVDM,2,2,3,B,T3kk855Ap3l4h00,2*79",
    "!AIVDM,1,1,,A,13P;lhP004wj=P8NShfP:bk608E`,0*0C",
    "!AIVDM,1,1,,A,13P8fQhP1Gwj@whNSh7cT?w<2<1:,0*73",
    "!AIVDM,1,1,,A,13M@DR@000Oj?>FNT`7H@K9F04sL,0*67",
    "!AIVDM,1,1,,A,34`vUp5000wj>48NS5rLUpiF0Dg:,0*0D",
    "!AIVDM,1,1,,B,13P;lhP004wj=PFNShj0MbmJ0@K;,0*3D",
    "!AIVDM,1,1,,B,34S93`5000Oj3pBNSdPol3ET0DMb,0*69",
    "!AIVDM,1,1,,A,13P;lhP002wj=PRNShk0u:od0002,0*63",
    "!AIVDM,1,1,,A,13M@DR@000Oj?>LNT`7`@K8600SK,0*17",
    "!AIVDM,1,1,,B,13P8fQhP1Owj@KrNSiPcg?v@285E,0*09",
    "!AIVDM,1,1,,B,13M@DR@000Oj?>VNT`6H@K8J0<1@,0*3E",
    "!AIVDM,1,1,,A,13P;lhP004wj=Q@NShj3mrlL089>,0*02",
    "!AIVDM,2,1,4,A,53ktrGT2E0:L=4tJ220@Tp610th58U>22222221650s;:4S=0>ihS2E`,0*25",
    "!AIVDM,2,2,4,A,888888888888880,2*20",
    "!AIVDM,1,1,,B,13P;lhP005wj=QlNShe5c:jh000f,0*18",
    "!AIVDM,1,1,,B,13M@DR@000Oj?>vNT`7p@K9200Sl,0*1C",
    "!AIVDM,1,1,,A,13P;lhP006wj=RBNSh`60ri604sP,0*04",
    "!AIVDM,1,1,,A,13P8fQhP1Kwj?mtNSjd;AOw<28FM,0*6E",
    "!AIVDM,1,1,,B,36Tbbj000uwj5l4NUUf<Mau>0061,0*5F",
    "!AIVDM,1,1,,A,13M@DR@000Oj??2NT`8`@K9F00Sd,0*39",
    "!AIVDM,1,1,,B,13P;lhP007wj=RnNShTUf:kJ0<12,0*35",
    "!AIVDM,1,1,,B,13P8fQhP1Ewj?bBNSk3cRgwP2@LK,0*77",
    "!AIVDM,1,1,,A,13P;lhP006wj=SLNShQ5Q:md0L12,0*1E",
    "!AIVDM,1,1,,A,13M@DR@000Oj?>hNT`8H@K860H1n,0*2B",
    "!AIVDM,1,1,,B,13P;lhP005wj=SvNShM5J:r8083Q,0*75",
    "!AIVDM,1,1,,B,13P8fQhP1?wj?F@NSkv;kOv@24sT,0*62",
    "!AIVDM,1,1,,A,33P;lhPOh5wj=T<NShM5=:v@0000,0*7F",
    "!AIVDM,1,1,,B,13M@DR@000Oj?>TNT`8`@K8J087O,0*17",
    "!AIVDM,1,1,,B,33P;lhPOh5wj=TFNShM5;JvF00sP,0*55",
    "!AIVDM,1,1,,A,33P;lhPOh5wj=TLNShK5Js0L018Q,0*15",
    "!AIVDM,1,1,,B,33P;lhPOh5wj=TbNShIUec0T0000,0*15",
    "!AIVDM,1,1,,A,33P;lhPOh5wj=TpNShHUqK2d00r0,0*49",
    "!AIVDM,1,1,,A,13M@DR@000Oj?>RNT`8p@K8h0<1@,0*2D",
    "!AIVDM,1,1,,B,33P;lhPOh4wj=U6NShG5Rs0j00o1,0*68",
    "!AIVDM,1,1,,A,33P;lhP003wj=U>NShG5Ac0p0000,0*04",
    "!AIVDM,1,1,,B,33P;lhP002wj=UFNShF52rvv011@,0*2D",
    "!AIVDM,1,1,,B,13M@DR@000Oj?>TNT`8`@K940<1@,0*65",
    "!AIVDM,1,1,,A,13P;lhP002wj=UNNShG4VJu600Rr,0*6B",
    "!AIVDM,1,1,,A,13P8fQhP1@wj>olNSm9cR?w<24sT,0*3F",
    "!AIVDM,1,1,,B,33ktrGU000wj@q<NSn9REJUF0D`J,0*20"
]

class MockMessageSource(Plugin):
    """
    Message Source that outputs valid AIS messages onto the event bus in a loop. 
    Messages are emitted at randomised intervals between min_delay and max_delay.
    """
    
    def __init__(
        self,
        bus: MessageBus,
        *,
        topic: str = "ais.raw",
        messages: list[str] | None = None,
        min_delay: float = 0.5,
        max_delay: float = 5.0,
    ) -> None:
        self.bus = bus
        self.topic = topic
        self.messages = messages or DEFAULT_MESSAGES
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

            with suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        idx = 0

        while True:
            msg = {"idx": idx, "text": self.messages[idx]}
            await self.bus.publish(self.topic, msg)

            idx = (idx + 1) % len(self.messages)
            await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

def make_plugin(bus: MessageBus, **kwargs: Any) -> Plugin:
    """
    Factory function required by the entry point.
    Receives the MessageBus from the core.
    """

    return MockMessageSource(bus, **kwargs)