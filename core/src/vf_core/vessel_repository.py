import aiosqlite
import logging
from typing import Any

class VesselRepository:
    def __init__(self, db_path: str) -> None:
        self._logger = logging.getLogger(__name__)
        self._db_path = db_path
        self._db_conn = None

    async def start(self) -> None:
        self._db_conn = await aiosqlite.connect(self._db_path)
        self._db_conn.row_factory = aiosqlite.Row
        await self._initialise_schema()

    async def _initialise_schema(self) -> None:
        if not self._db_conn:
            self._logger.error("Database not connected")
            return None
    
        await self._db_conn.execute("""
            CREATE TABLE IF NOT EXISTS vessels (
                mmsi TEXT PRIMARY KEY,
                imo TEXT,
                name TEXT,
                callsign TEXT,
                type INTEGER,
                bow INTEGER,
                stern INTEGER,
                port INTEGER,
                starboard INTEGER,
                first_sight INTEGER,
                last_sight INTEGER,
                has_static_data BOOLEAN DEFAULT FALSE,
                static_data_received INTEGER
            );
        """)
        await self._db_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_sight ON vessels(last_sight DESC);
        """)
        await self._db_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_has_static_data ON vessels(has_static_data);
        """)
        await self._db_conn.commit()

    async def upsert_vessel(
        self, vessel_data: dict[str, Any], allow_static_update: bool
    ) -> dict[str, Any] | None:
        if not self._db_conn:
            self._logger.error("Database not connected")
            return None
    
        query = """
            INSERT INTO vessels (
                mmsi, imo, name, callsign, type, bow, stern, port, starboard,
                first_sight, last_sight, has_static_data, static_data_received
            )
            VALUES (
                :mmsi, :imo, :name, :callsign, :ship_type, :bow, :stern, :port, :starboard,
                strftime('%s', 'now'), 
                strftime('%s', 'now'),
                :has_static_data,
                CASE WHEN :has_static_data = 1 THEN strftime('%s', 'now') ELSE NULL END
            )
            ON CONFLICT(mmsi) DO UPDATE SET 
                last_sight = excluded.last_sight
        """

        if allow_static_update:
            query += """,
                imo = excluded.imo,
                name = excluded.name,
                callsign = excluded.callsign,
                type = excluded.type,
                bow = excluded.bow,
                stern = excluded.stern,
                port = excluded.port,
                starboard = excluded.starboard,
                has_static_data = 1,
                static_data_received = COALESCE(static_data_received, excluded.static_data_received)
            """

        query += " RETURNING *;"

        try:
            cursor = await self._db_conn.execute(query, vessel_data)
            result = await cursor.fetchone()
            await self._db_conn.commit()

            if result is not None:
                return dict(result)

            return result
        except aiosqlite.Error as e:
            self._logger.exception("SQLite error")
            await self._db_conn.rollback()
            return None

    async def get_vessel(self, mmsi: str) -> dict[str, Any] | None:
        if not self._db_conn:
            self._logger.error("Database not connected")
            return None
    
        try:
            cursor = await self._db_conn.execute(
                "SELECT * FROM vessels WHERE mmsi = ?", (mmsi,)
            )
            result = await cursor.fetchone()
            if result:
                return dict(result)
            return None
        except aiosqlite.Error as e:
            self._logger.exception("Error fetching vessel")
            return None

    async def get_vessel_stats(self) -> dict[str, Any] | None:
        try:
            cursor = await self._db_conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN has_static_data = 1 THEN 1 ELSE 0 END) as identified,
                    SUM(CASE WHEN has_static_data = 0 THEN 1 ELSE 0 END) as unknown
                FROM vessels
            """)
            result = await cursor.fetchone()
            if result:
                stats = dict(result)
                if stats['total'] > 0:
                    stats['percent_identified'] = round(
                        100.0 * stats['identified'] / stats['total'], 1
                    )
                else:
                    stats['percent_identified'] = 0.0
                return stats
            return {'total': 0, 'identified': 0, 'unknown': 0, 'percent_identified': 0.0}
        except aiosqlite.Error as e:
            self._logger.exception("Error fetching stats")
            return None

    async def stop(self) -> None:
        if self._db_conn:
            await self._db_conn.close()