import asyncio
import time
import logging
import math
from contextlib import suppress
from .message_bus import MessageBus
from typing import Any
from .vessel_repository import VesselRepository

class VesselManager:
    def __init__(
        self,
        bus: MessageBus,
        repository: VesselRepository,
        *,
        in_topic: str = "ais.decoded",
        max_tracked: int = 50,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._bus = bus
        self._in_topic = in_topic
        self._max_tracked = max_tracked
        self._vessels: dict[str, Any] = {}
        self._task: asyncio.Task[None] | None = None
        self._vessel_repo = repository
        self._zones:list[dict[str, Any]] = []

    async def start(self) -> None:
        await self._vessel_repo.connect()

        if self._task and not self._task.done():
            return

        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

            with suppress(asyncio.CancelledError):
                await self._task

        if self._vessel_repo:
            await self._vessel_repo.close()

    async def _loop(self) -> None:
        try:
            async for msg in self._bus.subscribe(self._in_topic):
                try:
                    await self._update_vessel(msg)
                except Exception as e:
                    self._logger.exception("Exception in update_vessel", exc_info=e)

                await asyncio.sleep(0)
        except asyncio.CancelledError:
            self._logger.info("Receive loop cancelled")
            raise
        except Exception as e:
            self._logger.exception("Receive loop crashed", exc_info=e)
            raise

    async def _update_vessel(self, message: dict[str, Any]):
        msg_type = message["msg_type"]
        mmsi = message["mmsi"]

        # Ship MMSI should be 9 or more digits. Under 9 means it's
        # probably a base station, navigation aid etc
        str_mmsi = str(mmsi)
        if len(str_mmsi) < 9:
            self._logger.info(f"MMSI {str_mmsi} is not a ship. Skip update.")
            return

        # If the first 3 values of MMSI are 111 this is a SAR aircraft
        if str_mmsi.startswith("111"):
            return

        # Only message types 5 and 24 have static data (24 is split and needs different logic, skip for now)
        has_static_data = msg_type == 5

        # Make sure the database has a record of this ship.
        values = {
            "mmsi": message["mmsi"],
            "imo": message.get("imo", "0"),
            "name": message.get("shipname", "Unknown"),
            "callsign": message.get("callsign", "????"),
            "ship_type": message.get("ship_type", "-1"),
            "bow": message.get("to_bow", 0),
            "stern": message.get("to_stern", 0),
            "port": message.get("to_port", 0),
            "starboard": message.get("to_starboard", 0),
        }

        ship = await self._vessel_repo.upsert_vessel(values, has_static_data)
        if ship is None:
            self._logger.error(f"Failed to record ship {mmsi}, skipping update")
            return

        # Filter out known static data keys to leave only dynamic data
        key_filter = [
            "mmsi",
            "msg_type",
            "sentences",
            "callsign",
            "shipname",
            "ship_type",
            "to_bow",
            "to_stern",
            "to_port",
            "to_starboard",
        ]
        dynamic_data = {k: v for k, v in message.items() if k not in key_filter}

        ship_prev = self._vessels.get(mmsi, {})
        zone_prev = ship_prev.get("zone", None)

        lat = dynamic_data.get("lat")
        lon = dynamic_data.get("lon")

        if lat is not None and lon is not None:
            ship["zone"] = self._check_zones(lat, lon)

        self._vessels[mmsi] = {
            **ship_prev,
            **ship,
            **dynamic_data,
            **{"ts": int(time.time())},
        }

        # Trim the tracked vessel list down if it's over the max size
        self._vessels = dict(
            sorted(self._vessels.items(), key=lambda item: item[1]["ts"], reverse=True)[:self._max_tracked]
        )

        ship = self._vessels[mmsi]
        if ship.get("zone", None) != zone_prev:
            await self._bus.publish(("zone.enter", ship, zone_prev))

        self._logger.info(f"SHIP: {ship.get('name', 'Unknown')} {mmsi}, Zone: {ship.get('zone', 'None')}")
        await self._bus.publish("vessel.updated", ship)

    def _check_zones(self, ship_lat: float, ship_lon: float):
        if len(self._zones) == 0:
            self._logger.info("Zone check request but no zones present")
            return None

        for zone in self._zones:
            name, zone_lat, zone_lon, radius = zone

            zone_lat, zone_lon, ship_lat, ship_lon = map(math.radians, [zone_lat, zone_lon, ship_lat, ship_lon])
            a: float = (
                math.sin((ship_lat - zone_lat) / 2) ** 2
                + math.cos(zone_lat)
                * math.cos(ship_lat)
                * math.sin((ship_lon - zone_lon) / 2) ** 2
            )
            c: float = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

            EARTH_RADIUS: float = 6371
            distance: float = EARTH_RADIUS * c

            self._logger.info(f"Distance {distance} Radius {radius}")

            if distance <= radius:
                return name

        return None
