import uuid
from dataclasses import dataclass
from datetime import datetime

import aiosqlite


@dataclass
class SessionRecord:
    id: str
    mode: str
    scenario_name: str
    tools_enabled: bool
    headroom_enabled: bool
    created_at: str = ""
    duration_seconds: float = 0.0
    total_cost_usd: float = 0.0


@dataclass
class TurnRecord:
    session_id: str
    turn_index: int
    input_audio_tokens: int
    input_text_tokens: int
    output_audio_tokens: int
    output_text_tokens: int
    tool_call_tokens: int
    audio_duration_seconds: float
    cost_usd: float


class MetricsStore:
    def __init__(self, db_path: str = "metrics.db"):
        self._path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    scenario_name TEXT,
                    tools_enabled INTEGER NOT NULL,
                    headroom_enabled INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    duration_seconds REAL DEFAULT 0,
                    total_cost_usd REAL DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    input_audio_tokens INTEGER DEFAULT 0,
                    input_text_tokens INTEGER DEFAULT 0,
                    output_audio_tokens INTEGER DEFAULT 0,
                    output_text_tokens INTEGER DEFAULT 0,
                    tool_call_tokens INTEGER DEFAULT 0,
                    audio_duration_seconds REAL DEFAULT 0,
                    cost_usd REAL DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            await db.commit()

    async def create_session(
        self,
        mode: str,
        scenario_name: str,
        tools_enabled: bool,
        headroom_enabled: bool,
    ) -> str:
        session_id = str(uuid.uuid4())
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO sessions (id, mode, scenario_name, tools_enabled, headroom_enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, mode, scenario_name, int(tools_enabled), int(headroom_enabled), datetime.utcnow().isoformat()),
            )
            await db.commit()
        return session_id

    async def get_session(self, session_id: str) -> SessionRecord:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cur:
                row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Session not found: {session_id}")
        return SessionRecord(
            id=row["id"],
            mode=row["mode"],
            scenario_name=row["scenario_name"],
            tools_enabled=bool(row["tools_enabled"]),
            headroom_enabled=bool(row["headroom_enabled"]),
            created_at=row["created_at"],
            duration_seconds=row["duration_seconds"],
            total_cost_usd=row["total_cost_usd"],
        )

    async def insert_turn(self, turn: TurnRecord) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """INSERT INTO turns
                   (session_id, turn_index, created_at, input_audio_tokens, input_text_tokens,
                    output_audio_tokens, output_text_tokens, tool_call_tokens,
                    audio_duration_seconds, cost_usd)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    turn.session_id, turn.turn_index, datetime.utcnow().isoformat(),
                    turn.input_audio_tokens, turn.input_text_tokens,
                    turn.output_audio_tokens, turn.output_text_tokens,
                    turn.tool_call_tokens, turn.audio_duration_seconds, turn.cost_usd,
                ),
            )
            await db.commit()

    async def get_turns(self, session_id: str) -> list[TurnRecord]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY turn_index", (session_id,)
            ) as cur:
                rows = await cur.fetchall()
        return [
            TurnRecord(
                session_id=r["session_id"],
                turn_index=r["turn_index"],
                input_audio_tokens=r["input_audio_tokens"],
                input_text_tokens=r["input_text_tokens"],
                output_audio_tokens=r["output_audio_tokens"],
                output_text_tokens=r["output_text_tokens"],
                tool_call_tokens=r["tool_call_tokens"],
                audio_duration_seconds=r["audio_duration_seconds"],
                cost_usd=r["cost_usd"],
            )
            for r in rows
        ]

    async def delete_session(self, session_id: str) -> bool:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
            cur = await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await db.commit()
            return cur.rowcount > 0

    async def finalize_session(self, session_id: str, duration_seconds: float, total_cost_usd: float) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE sessions SET duration_seconds = ?, total_cost_usd = ? WHERE id = ?",
                (duration_seconds, total_cost_usd, session_id),
            )
            await db.commit()

    async def list_sessions(self) -> list[SessionRecord]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM sessions ORDER BY created_at DESC") as cur:
                rows = await cur.fetchall()
        return [
            SessionRecord(
                id=r["id"], mode=r["mode"], scenario_name=r["scenario_name"],
                tools_enabled=bool(r["tools_enabled"]), headroom_enabled=bool(r["headroom_enabled"]),
                created_at=r["created_at"], duration_seconds=r["duration_seconds"],
                total_cost_usd=r["total_cost_usd"],
            )
            for r in rows
        ]
