import json
import os
import random
import sqlite3
import sys
from pathlib import Path

EXPRESSION_NAMES: tuple[str, ...] = (
    "admiration", "adoration", "aesthetic_appreciation", "amusement", "anger",
    "anxiety", "awe", "awkwardness", "boredom", "calmness",
    "concentration", "confusion", "contemplation", "contempt", "contentment",
    "craving", "desire", "determination", "disappointment", "disgust",
    "distress", "doubt", "ecstasy", "embarrassment", "empathic_pain",
    "entrancement", "envy", "excitement", "fear", "guilt",
    "horror", "interest", "joy", "love", "nostalgia",
    "pain", "pride", "realization", "relief", "romance",
    "sadness", "satisfaction", "shame", "surprise_negative", "surprise_positive",
    "sympathy", "tiredness", "triumph",
)   # exactly 48 — Hume-style expression vocabulary
CREATIVE_DURATION_MS = 60_000
FACE_FRAME_INTERVAL_MS = 33
VOICE_INTERVAL_MS = 250
SESSION_STARTED_AT = "2026-07-12T10:00:00Z"
CREATIVES: tuple[tuple[str, str, str], ...] = (
    ("creative-spring-launch", "Spring Launch", "Acme"),
    ("creative-summer-splash", "Summer Splash", "Globex"),
    ("creative-winter-glow", "Winter Glow", "Initech"),
    ("creative-autumn-drive", "Autumn Drive", "Umbrella"),
)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: seed-source <session_id> [duration_ms]", file=sys.stderr)
        sys.exit(2)

    session_id = sys.argv[1]
    duration_ms = int(sys.argv[2]) if len(sys.argv) >= 3 else CREATIVE_DURATION_MS
    database_path = os.environ.get("SOURCE_DATABASE_PATH", "data/source.db")

    print(f"seeding session {session_id} into {database_path}")
    seed_source(database_path, session_id, duration_ms)

    reaction_count = len(range(0, duration_ms, FACE_FRAME_INTERVAL_MS)) + len(
        range(0, duration_ms, VOICE_INTERVAL_MS)
    )
    print(f"Seeded session {session_id!r} into {database_path!r} — {reaction_count} raw reactions")


def seed_source(database_path: str, session_id: str, duration_ms: int = CREATIVE_DURATION_MS) -> None:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    try:
        _create_schema(connection)
        rng = random.Random(session_id)
        _insert_viewer(connection, session_id, rng)
        creative_id = _insert_creative(connection, duration_ms, rng)
        _insert_session(connection, session_id, creative_id)
        _insert_reactions(connection, session_id, duration_ms, rng)
        connection.commit()
    finally:
        connection.close()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS viewers   (id TEXT PRIMARY KEY, age_bracket TEXT, gender TEXT, country_code TEXT);
        CREATE TABLE IF NOT EXISTS creatives (id TEXT PRIMARY KEY, title TEXT, brand TEXT, duration_ms INTEGER);
        CREATE TABLE IF NOT EXISTS sessions  (id TEXT PRIMARY KEY, viewer_id TEXT, creative_id TEXT, started_at TEXT);
        CREATE TABLE IF NOT EXISTS reactions (session_id TEXT, timestamp_ms INTEGER, channel TEXT, scores TEXT);
    """)


def _insert_viewer(connection: sqlite3.Connection, session_id: str, rng: random.Random) -> None:
    viewer_id = f"viewer-{session_id}"
    age_bracket = rng.choice(("18-24", "25-34", "35-44", "45-54"))
    gender = rng.choice(("female", "male", "nonbinary"))
    country_code = rng.choice(("PL", "US", "DE", "GB"))
    connection.execute(
        "INSERT OR REPLACE INTO viewers (id, age_bracket, gender, country_code) VALUES (?, ?, ?, ?)",
        (viewer_id, age_bracket, gender, country_code),
    )


def _insert_creative(connection: sqlite3.Connection, duration_ms: int, rng: random.Random) -> str:
    creative_id, title, brand = rng.choice(CREATIVES)
    connection.execute(
        "INSERT OR REPLACE INTO creatives (id, title, brand, duration_ms) VALUES (?, ?, ?, ?)",
        (creative_id, title, brand, duration_ms),
    )
    return creative_id


def _insert_session(connection: sqlite3.Connection, session_id: str, creative_id: str) -> None:
    viewer_id = f"viewer-{session_id}"
    connection.execute(
        "INSERT OR REPLACE INTO sessions (id, viewer_id, creative_id, started_at) VALUES (?, ?, ?, ?)",
        (session_id, viewer_id, creative_id, SESSION_STARTED_AT),
    )


def _insert_reactions(
    connection: sqlite3.Connection, session_id: str, duration_ms: int, rng: random.Random
) -> None:
    connection.execute("DELETE FROM reactions WHERE session_id = ?", (session_id,))

    rows: list[tuple[str, int, str, str]] = []
    for channel, interval_ms in (("face", FACE_FRAME_INTERVAL_MS), ("voice", VOICE_INTERVAL_MS)):
        scores: dict[str, float] = {name: rng.random() for name in EXPRESSION_NAMES}
        for timestamp_ms in range(0, duration_ms, interval_ms):
            if timestamp_ms > 0:
                scores = {
                    name: max(0.0, min(1.0, scores[name] + rng.uniform(-0.05, 0.05)))
                    for name in EXPRESSION_NAMES
                }
            rows.append((session_id, timestamp_ms, channel, json.dumps(scores)))

    connection.executemany(
        "INSERT INTO reactions (session_id, timestamp_ms, channel, scores) VALUES (?, ?, ?, ?)",
        rows,
    )
