import aiosqlite
from app.config import settings

_db: aiosqlite.Connection | None = None

SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS questions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint   TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    options       TEXT DEFAULT '',
    type          TEXT NOT NULL DEFAULT '',
    answer        TEXT NOT NULL,
    options_hash  TEXT DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    query_count   INTEGER NOT NULL DEFAULT 1
)
"""

SCHEMA_INDEX = """
CREATE INDEX IF NOT EXISTS idx_questions_fingerprint ON questions (fingerprint)
"""


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(settings.database_path)
        _db.row_factory = aiosqlite.Row
        await _db.execute(SCHEMA_TABLE)
        await _db.execute(SCHEMA_INDEX)
        await _db.commit()
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def get_question(fingerprint: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM questions WHERE fingerprint = ?", (fingerprint,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    await db.execute(
        "UPDATE questions SET query_count = query_count + 1, updated_at = datetime('now') WHERE fingerprint = ?",
        (fingerprint,),
    )
    await db.commit()
    return dict(row)


async def insert_question(
    fingerprint: str,
    title: str,
    options: str,
    qtype: str,
    answer: str,
    options_hash: str,
) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO questions (fingerprint, title, options, type, answer, options_hash)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (fingerprint, title, options, qtype, answer, options_hash),
    )
    await db.commit()


async def upsert_question(
    fingerprint: str,
    title: str,
    options: str,
    qtype: str,
    answer: str,
    options_hash: str,
) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO questions (fingerprint, title, options, type, answer, options_hash)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(fingerprint) DO UPDATE SET
               answer = excluded.answer,
               options_hash = excluded.options_hash,
               updated_at = datetime('now'),
               query_count = query_count + 1""",
        (fingerprint, title, options, qtype, answer, options_hash),
    )
    await db.commit()


async def get_stats() -> dict:
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) as total FROM questions")
    row = await cursor.fetchone()
    return {"total": row["total"]}
