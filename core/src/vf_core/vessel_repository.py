import aiosqlite
import logging

class VesselRepository:
    def __init__(self, db_path:str) -> None:
        self._logger = logging.getLogger(__name__)
        self._db_path = db_path
        self._db_conn = None

    async def connect(self) -> None:
        self._db_conn = await aiosqlite.connect(self._db_path)
        self._db_conn.row_factory = aiosqlite.Row
        
        await self._initialise_schema()

    async def _initialise_schema(self) -> None:
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
                last_sight INTEGER
            );""")
        await self._db_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_sight ON vessels(last_sight DESC);
        """)
        await self._db_conn.commit()

    async def upsert_vessel(self, vessel_data: dict, allow_update: bool) -> dict | None:
        if self._db_conn is None:
            raise RuntimeError("Attempt to upsert before database connected.")
    
        query = """
            INSERT INTO vessels (mmsi, imo, name, callsign, type, bow, stern, port, starboard, first_sight, last_sight)
            VALUES(:mmsi, :imo, :name, :callsign, :ship_type, :bow, :stern, :port, :starboard, strftime('%s', 'now'), strftime('%s', 'now'))
            ON CONFLICT(mmsi) DO UPDATE SET 
        """

        if allow_update:
            query += """
                    imo = excluded.imo,
                    name = excluded.name,
                    callsign = excluded.callsign,
                    type = excluded.type,
                    bow = excluded.bow,
                    stern = excluded.stern,
                    port = excluded.port,
                    starboard = excluded.starboard,
        """
            
        query += "last_sight = excluded.last_sight RETURNING *;"

        try:
            cursor = await self._db_conn.execute(query, vessel_data)
            result = await cursor.fetchone()

            await self._db_conn.commit()

            if result is not None:
                result = dict(result)

            return result
        except aiosqlite.Error as e:
            self._logger.exception("SQLite error", exc_info=e)
            await self._db_conn.rollback()

        return None
    
    async def close(self) -> None:
        if self._db_conn:
            await self._db_conn.close()