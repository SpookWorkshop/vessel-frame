import asyncio
import time
import logging
import math
from contextlib import suppress
from .message_bus import MessageBus
from typing import Any
from .vessel_repository import VesselRepository


class VesselManager:
    # Event topics published by VesselManager
    EVENT_APPEARED = "vessel.appeared"
    EVENT_FIRST_SEEN = "vessel.first_seen"
    EVENT_IDENTIFIED = "vessel.identified"
    EVENT_ZONE_ENTERED = "vessel.zone_entered"
    EVENT_ZONE_EXITED = "vessel.zone_exited"
    EVENT_ZONE_MOVED = "vessel.zone_moved"
    EVENT_UPDATED = "vessel.updated"

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
        """
        Start tracking vessels from data received via the message bus.

        Creates and runs the asynchronous background task that processes
        decoded AIS messages from the subscribed topic.
        """
        if self._task and not self._task.done():
            return

        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """
        Stop the background data listener task.

        Cancels the running loop and waits for clean shutdown. Safe to call
        multiple times.
        """
        if self._task and not self._task.done():
            self._task.cancel()

            with suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        """Main receive loop that subscribes to data messages and processes them."""
        try:
            async for msg in self._bus.subscribe(self._in_topic):
                try:
                    await self._update_vessel(msg)
                except Exception as e:
                    self._logger.exception("Exception in update_vessel")

                await asyncio.sleep(0)
        except asyncio.CancelledError:
            self._logger.info("Receive loop cancelled")
            raise
        except Exception as e:
            self._logger.exception("Receive loop crashed")
            raise

    def _is_message_valid(self, message: dict[str, Any]) -> bool:
        """
        Check whether a received decoded message should be processed.

        Filters out non-ship MMSI numbers such as base stations and SAR aircraft.

        Args:
            message (dict[str, Any]): Decoded AIS message.

        Returns:
            bool: True if the message represents a valid ship, otherwise False.
        """
        mmsi = str(message["mmsi"])

        # Ship MMSI should be 9 or more digits. Under 9 means it's
        # probably a base station, navigation aid etc
        if len(mmsi) != 9:
            self._logger.debug(f"MMSI {mmsi} is not a ship. Skip update.")
            return False

        # If the first 3 values of MMSI are 111 this is a SAR aircraft
        if mmsi.startswith("111"):
            return False

        return True

    async def _update_vessel(self, message: dict[str, Any]) -> None:
        """
        Process an incoming decoded message and update vessel details.

        Updates or inserts vessel information in memory and the repository,
        determines zone membership, and publishes events for new, updated,
        or moved vessels.

        Args:
            message (dict[str, Any]): The decoded AIS message data.
        """
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
            "ship_type": message.get("ship_type", -1),
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
                self._logger.info(
                    f"Returning vessel: {db_vessel.get('name', 'Unknown')} ({mmsi})"
                )
                ship_prev = db_vessel

                # Publish first_seen event (first seen in this session, not ever)
                await self._bus.publish(
                    self.EVENT_APPEARED,
                    {
                        "mmsi": mmsi,
                        "vessel": db_vessel,
                        "known": db_vessel.get("has_static_data", False),
                    },
                )
            else:
                # Brand new vessel
                self._logger.info(f"New vessel detected: {mmsi}")
                await self._bus.publish(
                    self.EVENT_FIRST_SEEN,
                    {"mmsi": mmsi, "has_static_data": has_static_data},
                )
        else:
            ship_prev = self._vessels[mmsi]

        # Upsert to database (always insert, conditionally update static data)
        ship = await self._vessel_repo.upsert_vessel(
            values, allow_static_update=has_static_data
        )
        if ship is None:
            self._logger.error(f"Failed to record ship {mmsi}, skipping update")
            return

        # Check if static data was just discovered
        if has_static_data and not ship_prev.get("has_static_data", False):
            self._logger.info(
                f"Vessel identified: {ship.get('name')} ({mmsi}), "
                f"Type: {ship.get('type', 'Unknown')}"
            )
            await self._bus.publish(
                self.EVENT_IDENTIFIED, {"mmsi": mmsi, "vessel": ship}
            )

        # Extract dynamic data (position, speed etc.)
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
            "imo",
            "has_static_data",
        ]
        dynamic_data = {k: v for k, v in message.items() if k not in key_filter}

        # Update current zone
        zone_prev = ship_prev.get("zone")
        lat = dynamic_data.get("lat")
        lon = dynamic_data.get("lon")
        if lat is not None and lon is not None:
            ship["zone"] = self._check_zones(lat, lon)

        # Update in-memory state. We merge these in a specific order:
        # - ship_prev: The ship data we already have
        # - ship: Augment with static values from database
        # - dynamic_data: Any transient data from the current message
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
                    self._vessels.items(), key=lambda item: item[1]["ts"], reverse=True
                )[: self._max_tracked]
            )

        # Publish zone events
        ship = self._vessels[mmsi]
        zone_current = ship.get("zone")

        if zone_current != zone_prev:
            if zone_prev is None and zone_current is not None:
                # Entered a zone
                await self._bus.publish(
                    self.EVENT_ZONE_ENTERED,
                    {"mmsi": mmsi, "zone": zone_current, "vessel": ship},
                )

                self._logger.info(
                    f"Vessel {ship.get('name', 'Unknown')} entered zone: {zone_current}"
                )
            elif zone_prev is not None and zone_current is None:
                # Exited a zone
                await self._bus.publish(
                    self.EVENT_ZONE_EXITED,
                    {"mmsi": mmsi, "zone": zone_prev, "vessel": ship},
                )

                self._logger.info(
                    f"Vessel {ship.get('name', 'Unknown')} exited zone: {zone_prev}"
                )
            elif zone_prev is not None and zone_current is not None:
                # Moved between zones
                await self._bus.publish(
                    self.EVENT_ZONE_MOVED,
                    {
                        "mmsi": mmsi,
                        "from_zone": zone_prev,
                        "to_zone": zone_current,
                        "vessel": ship,
                    },
                )

                self._logger.info(
                    f"Vessel {ship.get('name', 'Unknown')} moved: {zone_prev} -> {zone_current}"
                )

        # Always publish vessel update
        self._logger.debug(
            f"Updated: {ship.get('name', 'Unknown')} ({mmsi}), Zone: {zone_current or 'None'}"
        )
        await self._bus.publish(self.EVENT_UPDATED, ship)

    def _calculate_distance(
        self, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """
        Calculate the great-circle distance between two coordinates.

        Uses the haversine formula to compute the distance in kilometres.

        Args:
            lat1 (float): Latitude of the first point in decimal degrees.
            lon1 (float): Longitude of the first point in decimal degrees.
            lat2 (float): Latitude of the second point in decimal degrees.
            lon2 (float): Longitude of the second point in decimal degrees.

        Returns:
            float: Distance between the two coordinates in kilometres.
        """
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        EARTH_RADIUS = 6371.0
        return EARTH_RADIUS * c

    def _check_zones(self, ship_lat: float, ship_lon: float) -> str | None:
        """
        Determine whether a vessel is inside a defined zone.

        Args:
            ship_lat (float): Vessel latitude.
            ship_lon (float): Vessel longitude.

        Returns:
            str | None: Name of the zone the vessel is currently in,
            or None if outside all zones.
        """
        if not self._zones:
            return None

        for zone in self._zones:
            distance = self._calculate_distance(
                ship_lat, ship_lon, zone["lat"], zone["lon"]
            )

            if distance <= zone["radius"]:
                self._logger.debug(
                    f"Vessel in zone '{zone['name']}' (distance: {distance:.2f}km)"
                )
                return zone["name"]

        return None

    def get_vessel(self, mmsi: str) -> dict[str, Any] | None:
        """Retrieve a tracked vessel by its MMSI."""
        return self._vessels.get(mmsi)

    def get_all_vessels(self) -> list[dict[str, Any]]:
        """Return all vessels currently tracked in memory."""
        return list(self._vessels.values())

    def get_identified_vessels(self) -> list[dict[str, Any]]:
        """Return all in-memory vessels for which we have identifying information (name, callsign)."""
        return [v for v in self._vessels.values() if v.get("has_static_data")]

    def get_unknown_vessels(self) -> list[dict[str, Any]]:
        """Return all in-memory vessels for which we currently have not identifying information (name, callsign)."""
        return [v for v in self._vessels.values() if not v.get("has_static_data")]

    def get_vessels_in_zone(self, zone_name: str) -> list[dict[str, Any]]:
        """
        Return all in-memory vessels currently within a given zone.

        Args:
            zone_name (str): The name of the zone to query.

        Returns:
            list[dict[str, Any]]: A list of vessels currently inside the specified zone.
        """
        return [v for v in self._vessels.values() if v.get("zone") == zone_name]

    def get_recent_vessels(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Return the most recently updated in-memory vessels.

        Args:
            limit (int, optional): Maximum number of vessels to return. Defaults to 20.

        Returns:
            list[dict[str, Any]]: A list of the most recently updated vessel records.
        """
        return sorted(
            self._vessels.values(), key=lambda v: v.get("ts", 0), reverse=True
        )[:limit]
