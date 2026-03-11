import json
import aiosqlite
import logging
from typing import Any


class VesselRepository:
    def __init__(self, db_path: str) -> None:
        self._logger = logging.getLogger(__name__)
        self._db_path = db_path
        self._db_conn = None

    async def start(self) -> None:
        """Connect to the database and initialise the schema if needed."""
        self._db_conn = await aiosqlite.connect(self._db_path)
        self._db_conn.row_factory = aiosqlite.Row
        await self._initialise_schema()

    async def _initialise_schema(self) -> None:
        """Create the database schema if it does not already exist."""
        if not self._db_conn:
            self._logger.error("Database not connected")
            return

        await self._db_conn.execute("""
            CREATE TABLE IF NOT EXISTS vessels (
                identifier  TEXT PRIMARY KEY,
                source_type TEXT NOT NULL DEFAULT 'ais',
                name        TEXT,
                first_sight INTEGER,
                last_sight  INTEGER,
                extension   TEXT
            );
        """)
        await self._db_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_sight ON vessels (last_sight DESC);
        """)
        await self._db_conn.commit()

        """

        """
        extension_json = row.pop("extension", None)
        if extension_json:
            try:
                row.update(json.loads(extension_json))
            except (json.JSONDecodeError, TypeError):
                self._logger.warning("Failed to decode extension JSON for vessel")
        return row

    async def upsert_vessel(
        self, vessel_data: dict[str, Any], allow_static_update: bool
    ) -> dict[str, Any] | None:
        """
        Insert or update a vessel record in the database.

        On first sighting the vessel is inserted with full extension data.
        On subsequent updates, the record's last_sight timestamp is updated. Static fields
        (name and extension) are updated only if allow_static_update is True.
        static_data_received is preserved once set, never overwritten.

        Args:
            vessel_data: Flat dict with identifier, source_type, name, and
                source-type-specific fields used to build the extension JSON.
            allow_static_update: Whether to update static information such
              as name, type, or dimensions.

        Returns:
            The upserted vessel record as a flat dict (extension unpacked),
            or None if an error occurred.
        """
        if not self._db_conn:
            self._logger.error("Database not connected")
            return None

        has_static_data = bool(vessel_data.get("has_static_data", 0))
        extension = self._build_extension(vessel_data, has_static_data)

        params = {
            "identifier":  vessel_data["identifier"],
            "source_type": vessel_data.get("source_type", "ais"),
            "name":        vessel_data.get("name", "Unknown"),
            "extension":   extension,
        }

        query = """
            INSERT INTO vessels (identifier, source_type, name, first_sight, last_sight, extension)
            VALUES (:identifier, :source_type, :name,
                    strftime('%s', 'now'), strftime('%s', 'now'), :extension)
            ON CONFLICT(identifier) DO UPDATE SET
                last_sight = excluded.last_sight
        """

        if has_name:
            query += ",\n name = excluded.name"

        if has_extension:
            query += """,
                extension = CASE
                    WHEN vessels.extension IS NULL THEN excluded.extension
                    ELSE json_patch(vessels.extension, excluded.extension)
                END"""

        query += "\n RETURNING *;"

        try:
            cursor = await self._db_conn.execute(query, params)
            result = await cursor.fetchone()
            await self._db_conn.commit()

            if result is not None:
                return self._unpack_row(dict(result))
            return None
        except aiosqlite.Error:
            self._logger.exception("SQLite error in upsert_vessel")
            await self._db_conn.rollback()
            return None

    async def get_vessel(self, identifier: str) -> dict[str, Any] | None:
        """
        Fetch a vessel record by its identifier.

        Args:
            identifier: The vessel's source-type identifier (MMSI for AIS).

        Returns:
            The vessel record as a flat dict (extension unpacked), or None if
            not found.
        """
        if not self._db_conn:
            self._logger.error("Database not connected")
            return None

        try:
            cursor = await self._db_conn.execute(
                "SELECT * FROM vessels WHERE identifier = ?", (identifier,)
            )
            result = await cursor.fetchone()
            if result:
                return self._unpack_row(dict(result))
            return None
        except aiosqlite.Error:
            self._logger.exception("Error fetching vessel")
            return None

    async def get_vessel_stats(self) -> dict[str, Any] | None:
        """
        Return aggregate statistics for tracked vessels.

        Returns:
            dict with total, identified, unknown, and percent_identified,
            or None if an error occurred.
        """
        if not self._db_conn:
            self._logger.error("Database not connected")
            return None

        try:
            cursor = await self._db_conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN extension IS NOT NULL THEN 1 ELSE 0 END) as identified,
                    SUM(CASE WHEN extension IS NULL     THEN 1 ELSE 0 END) as unknown
                FROM vessels
            """)
            result = await cursor.fetchone()
            if result:
                stats = dict(result)
                if stats["total"] > 0:
                    stats["percent_identified"] = round(
                        100.0 * stats["identified"] / stats["total"], 1
                    )
                else:
                    stats["percent_identified"] = 0.0
                return stats
            return {
                "total": 0,
                "identified": 0,
                "unknown": 0,
                "percent_identified": 0.0,
            }
        except aiosqlite.Error:
            self._logger.exception("Error fetching vessel stats")
            return None

    async def stop(self) -> None:
        """Close the database connection if open."""
        if self._db_conn:
            await self._db_conn.close()
