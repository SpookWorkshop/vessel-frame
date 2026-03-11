import json
import time
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
        """
        Create the database schema if it does not already exist.

        Detects and migrates the legacy per-column AIS schema to the generic
        identifier + extension JSON layout
        """
        if not self._db_conn:
            self._logger.error("Database not connected")
            return

        # Detect legacy schema: vessels table with an 'mmsi' column.
        cursor = await self._db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vessels'"
        )
        if await cursor.fetchone():
            cursor = await self._db_conn.execute("PRAGMA table_info(vessels)")
            columns = {row[1] for row in await cursor.fetchall()}
            if "mmsi" in columns:
                await self._migrate_legacy_schema()

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

    async def _migrate_legacy_schema(self) -> None:
        """
        Migrate from the old per-column AIS schema to the generic extension JSON schema.

        Packs imo, callsign, type, bow, stern, port, starboard, has_static_data, and
        static_data_received into a JSON extension column. The 'mmsi' primary key
        becomes 'identifier'. Runs inside a single transaction.
        """
        self._logger.info("Migrating vessels database.")
        try:
            await self._db_conn.execute("""
                CREATE TABLE vessels_new (
                    identifier  TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL DEFAULT 'ais',
                    name        TEXT,
                    first_sight INTEGER,
                    last_sight  INTEGER,
                    extension   TEXT
                );
            """)
            await self._db_conn.execute("""
                INSERT INTO vessels_new
                    (identifier, source_type, name, first_sight, last_sight, extension)
                SELECT
                    mmsi,
                    'ais',
                    name,
                    first_sight,
                    last_sight,
                    json_object(
                        'mmsi',                 mmsi,
                        'imo',                  imo,
                        'callsign',             callsign,
                        'ship_type',            type,
                        'ship_type_name',       NULL,
                        'bow',                  bow,
                        'stern',                stern,
                        'port',                 port,
                        'starboard',            starboard,
                        'has_static_data',      has_static_data,
                        'static_data_received', static_data_received
                    )
                FROM vessels;
            """)
            await self._db_conn.execute("DROP TABLE vessels;")
            await self._db_conn.execute("ALTER TABLE vessels_new RENAME TO vessels;")
            await self._db_conn.commit()
            self._logger.info("Database migration complete.")
        except aiosqlite.Error:
            self._logger.exception("Database migration failed")
            await self._db_conn.rollback()
            raise

    def _build_extension(self, vessel_data: dict[str, Any], has_static_data: bool) -> str:
        """Pack AIS-specific fields from vessel_data into a JSON extension string."""
        return json.dumps({
            "mmsi":                 vessel_data.get("mmsi"),
            "imo":                  vessel_data.get("imo", "0"),
            "callsign":             vessel_data.get("callsign", "????"),
            "ship_type":            vessel_data.get("ship_type", -1),
            "ship_type_name":       vessel_data.get("ship_type_name", "Unknown"),
            "bow":                  vessel_data.get("bow", 0),
            "stern":                vessel_data.get("stern", 0),
            "port":                 vessel_data.get("port", 0),
            "starboard":            vessel_data.get("starboard", 0),
            "has_static_data":      has_static_data,
            "static_data_received": int(time.time()) if has_static_data else None,
        })

    def _unpack_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Unpack the extension JSON column into the flat vessel dict."""
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

        if allow_static_update:
            # Update name and extension. For static_data_received, preserve the
            # original timestamp using COALESCE so it records the first Type 5.
            query += """,
                name = excluded.name,
                extension = json_patch(
                    excluded.extension,
                    json_object(
                        'static_data_received',
                        COALESCE(
                            json_extract(vessels.extension, '$.static_data_received'),
                            json_extract(excluded.extension, '$.static_data_received')
                        )
                    )
                )
            """

        query += " RETURNING *;"

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
                    SUM(CASE WHEN json_extract(extension, '$.has_static_data') = 1
                             THEN 1 ELSE 0 END) as identified,
                    SUM(CASE WHEN json_extract(extension, '$.has_static_data') != 1
                             THEN 1 ELSE 0 END) as unknown
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
