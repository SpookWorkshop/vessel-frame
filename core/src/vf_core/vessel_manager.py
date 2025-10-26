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
        self._vessels: dict[str, dict[str, Any]] = {}
        self._task: asyncio.Task[None] | None = None
        self._vessel_repo = repository
        self._zones: list[dict[str, Any]] = []

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

    def _is_message_valid(self, message: dict[str, Any]) -> bool:
        mmsi = str(message["mmsi"])

        # Ship MMSI should be 9 or more digits. Under 9 means it's
        # probably a base station, navigation aid etc
        if len(mmsi) < 9:
            self._logger.debug(f"MMSI {mmsi} is not a ship. Skip update.")
            return False

        # If the first 3 values of MMSI are 111 this is a SAR aircraft
        if mmsi.startswith("111"):
            return False
        
        return True

    async def _update_vessel(self, message: dict[str, Any]) -> None:
        if not self._is_message_valid(message):
            return

        msg_type = message["msg_type"]
        mmsi = str(message["mmsi"])
        
        # Check if this is a new vessel we haven't seen before
        is_new_vessel = mmsi not in self._vessels

        # Type 5 messages have static data
        has_static_data = msg_type == 5

        # Prepare vessel data (always include defaults)
        values = {
            "mmsi": mmsi,
            "imo": message.get("imo", "0"),
            "name": message.get("shipname", "Unknown"),
            "callsign": message.get("callsign", "????"),
            "ship_type": message.get("ship_type", "-1"),
            "bow": message.get("to_bow", 0),
            "stern": message.get("to_stern", 0),
            "port": message.get("to_port", 0),
            "starboard": message.get("to_starboard", 0),
            "has_static_data": 1 if has_static_data else 0,
        }

        # If new vessel, try to load from database first
        ship_prev = {}
        if is_new_vessel:
            db_vessel = await self._vessel_repo.get_vessel(mmsi)
            if db_vessel:
                # We've seen this vessel before
                self._logger.info(f"Returning vessel: {db_vessel.get('name', 'Unknown')} ({mmsi})")
                ship_prev = db_vessel
                
                # Publish first_seen event (first seen in this session, not ever)
                await self._bus.publish("vessel.appeared", {
                    "mmsi": mmsi,
                    "vessel": db_vessel,
                    "known": db_vessel.get('has_static_data', False)
                })
            else:
                # Brand new vessel
                self._logger.info(f"New vessel detected: {mmsi}")
                await self._bus.publish("vessel.first_seen", {
                    "mmsi": mmsi,
                    "has_static_data": has_static_data
                })
        else:
            ship_prev = self._vessels[mmsi]

        # Upsert to database (always insert, conditionally update static data)
        ship = await self._vessel_repo.upsert_vessel(values, allow_static_update=has_static_data)
        if ship is None:
            self._logger.error(f"Failed to record ship {mmsi}, skipping update")
            return

        # Check if static data was just discovered
        if has_static_data and not ship_prev.get('has_static_data', False):
            self._logger.info(
                f"Vessel identified: {ship.get('name')} ({mmsi}), "
                f"Type: {ship.get('type', 'Unknown')}"
            )
            await self._bus.publish("vessel.identified", {
                "mmsi": mmsi,
                "vessel": ship
            })

        # Extract dynamic data (position, speed etc.)
        key_filter = [
            "mmsi", "msg_type", "sentences", "callsign", "shipname",
            "ship_type", "to_bow", "to_stern", "to_port", "to_starboard",
            "imo", "has_static_data"
        ]
        dynamic_data = {k: v for k, v in message.items() if k not in key_filter}

        # Update current zone
        zone_prev = ship_prev.get("zone")
        lat = dynamic_data.get("lat")
        lon = dynamic_data.get("lon")
        if lat is not None and lon is not None:
            ship["zone"] = self._check_zones(lat, lon)

        # Update in-memory state
        self._vessels[mmsi] = {
            **ship_prev,
            **ship,
            **dynamic_data,
            "ts": int(time.time()),
        }

        # Trim if over max
        if len(self._vessels) > self._max_tracked:
            self._vessels = dict(
                sorted(
                    self._vessels.items(),
                    key=lambda item: item[1]["ts"],
                    reverse=True
                )[:self._max_tracked]
            )

        # Publish zone events
        ship = self._vessels[mmsi]
        zone_current = ship.get("zone")
        
        if zone_current != zone_prev:
            if zone_prev is None and zone_current is not None:
                # Entered a zone
                await self._bus.publish("vessel.zone_entered", {
                    "mmsi": mmsi,
                    "zone": zone_current,
                    "vessel": ship
                })

                self._logger.info(f"Vessel {ship.get('name', 'Unknown')} entered zone: {zone_current}")
            elif zone_prev is not None and zone_current is None:
                # Exited a zone
                await self._bus.publish("vessel.zone_exited", {
                    "mmsi": mmsi,
                    "zone": zone_prev,
                    "vessel": ship
                })

                self._logger.info(f"Vessel {ship.get('name', 'Unknown')} exited zone: {zone_prev}")
            elif zone_prev is not None and zone_current is not None:
                # Moved between zones
                await self._bus.publish("vessel.zone_moved", {
                    "mmsi": mmsi,
                    "from_zone": zone_prev,
                    "to_zone": zone_current,
                    "vessel": ship
                })

                self._logger.info(f"Vessel {ship.get('name', 'Unknown')} moved: {zone_prev} -> {zone_current}")

        # Always publish vessel update
        self._logger.debug("Updated: {ship.get('name', 'Unknown')} ({mmsi}), Zone: {zone_current or 'None'}")
        await self._bus.publish("vessel.updated", ship)

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        EARTH_RADIUS = 6371.0
        return EARTH_RADIUS * c

    def _check_zones(self, ship_lat: float, ship_lon: float) -> str | None:
        if not self._zones:
            return None
        
        for zone in self._zones:
            distance = self._calculate_distance(ship_lat, ship_lon, zone['lat'], zone['lon'])
            
            if distance <= zone['radius']:
                self._logger.debug(f"Vessel in zone '{zone['name']}' (distance: {distance:.2f}km)")
                return zone['name']
        
        return None
    
    def get_vessel(self, mmsi: str) -> dict[str, Any] | None:
        return self._vessels.get(mmsi)

    def get_all_vessels(self) -> list[dict[str, Any]]:
        return list(self._vessels.values())

    def get_identified_vessels(self) -> list[dict[str, Any]]:
        return [v for v in self._vessels.values() if v.get('has_static_data')]

    def get_unknown_vessels(self) -> list[dict[str, Any]]:
        return [v for v in self._vessels.values() if not v.get('has_static_data')]

    def get_vessels_in_zone(self, zone_name: str) -> list[dict[str, Any]]:
        return [v for v in self._vessels.values() if v.get('zone') == zone_name]

    def get_recent_vessels(self, limit: int = 20) -> list[dict[str, Any]]:
        return sorted(
            self._vessels.values(),
            key=lambda v: v.get('ts', 0),
            reverse=True
        )[:limit]
