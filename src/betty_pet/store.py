"""Persistence for pet state, settings and a small event log.

The SQLite store keeps four tables:

* ``pet_state``   - a single row holding the current stats, affection and
  their timestamp.
* ``settings``    - key/value pairs for user preferences such as window scale.
* ``event_log``   - an append-only trace of recoveries, actions and lifecycle
  events. It is deliberately lossy: :meth:`SQLiteStateStore.prune_events`
  keeps the log bounded so a pet left running for months does not grow a
  database without limit.
* ``daily_usage`` - per-day counters keyed by ``(day, key)``, used to enforce
  item daily limits that reset at local midnight.

Schema changes are applied through :data:`ADDED_COLUMNS` so an older save file
is migrated in place instead of being discarded.

Everything stays local. Nothing in here talks to the network.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Protocol

from .state import PetState, PetStats

__all__ = ["StateStore", "SQLiteStateStore", "MemoryStateStore", "DEFAULT_DB_PATH"]


DEFAULT_DB_PATH = Path.home() / ".betty_pet" / "state.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pet_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    hunger REAL NOT NULL,
    mood REAL NOT NULL,
    energy REAL NOT NULL,
    affection REAL NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS daily_usage (
    day TEXT NOT NULL,
    key TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, key)
);
"""

# Columns added after the first release. Applied to databases created by older
# versions so an existing save file keeps working instead of being discarded.
ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("pet_state", "affection", "REAL NOT NULL DEFAULT 0"),
)


def local_day(moment: datetime | None = None) -> str:
    """Local calendar day as ``YYYY-MM-DD``. Daily limits reset at local midnight."""
    return (moment or datetime.now()).astimezone().strftime("%Y-%m-%d")


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _parse(text: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class StateStore(Protocol):
    """Load/save contract so the window does not care about the backend."""

    def load(self) -> PetState: ...

    def save(self, state: PetState) -> None: ...


class SQLiteStateStore:
    """SQLite-backed store. Created lazily so a missing file is not an error."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path).expanduser()
        if self.db_path.parent != Path(""):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self._transaction() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        for table, column, definition in ADDED_COLUMNS:
            existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def load(self) -> PetState:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT hunger, mood, energy, affection, last_updated FROM pet_state WHERE id = 1"
            ).fetchone()
        if row is None:
            return PetState()
        hunger, mood, energy, affection, last_updated = row
        return PetState(
            stats=PetStats(hunger=hunger, mood=mood, energy=energy).clamp(),
            affection=max(0.0, float(affection)),
            last_updated=_parse(last_updated),
        )

    def save(self, state: PetState) -> None:
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO pet_state (id, hunger, mood, energy, affection, last_updated) "
                "VALUES (1, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET hunger = excluded.hunger, "
                "mood = excluded.mood, energy = excluded.energy, "
                "affection = excluded.affection, "
                "last_updated = excluded.last_updated",
                (
                    state.stats.hunger,
                    state.stats.mood,
                    state.stats.energy,
                    state.affection,
                    _iso(state.last_updated),
                ),
            )

    def daily_count(self, key: str, day: str | None = None) -> int:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT count FROM daily_usage WHERE day = ? AND key = ?", (day or local_day(), key)
            ).fetchone()
        return int(row[0]) if row else 0

    def bump_daily(self, key: str, day: str | None = None) -> int:
        """Record one use and return the new count for that day."""
        stamp = day or local_day()
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO daily_usage (day, key, count) VALUES (?, ?, 1) "
                "ON CONFLICT(day, key) DO UPDATE SET count = count + 1",
                (stamp, key),
            )
            row = connection.execute(
                "SELECT count FROM daily_usage WHERE day = ? AND key = ?", (stamp, key)
            ).fetchone()
        return int(row[0]) if row else 1

    def log_event(self, kind: str, detail: dict | None = None) -> None:
        payload = json.dumps(detail or {}, ensure_ascii=False)
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO event_log (ts, kind, detail) VALUES (?, ?, ?)",
                (_iso(datetime.now(timezone.utc)), kind, payload),
            )

    def recent_events(self, limit: int = 20) -> list[tuple[str, str, str]]:
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT ts, kind, detail FROM event_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [(str(ts), str(kind), str(detail)) for ts, kind, detail in rows]

    def prune_events(self, keep: int = 500) -> int:
        """Drop all but the newest ``keep`` events. Returns rows deleted."""
        with self._transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM event_log WHERE id NOT IN "
                "(SELECT id FROM event_log ORDER BY id DESC LIMIT ?)",
                (keep,),
            )
            return cursor.rowcount if cursor.rowcount > 0 else 0

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._transaction() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


class MemoryStateStore:
    """In-memory fallback used by ``--no-persist`` and by tests."""

    def __init__(self) -> None:
        self.state = PetState()
        self.settings: dict[str, str] = {}
        self.events: list[tuple[str, str, str]] = []
        self.daily: dict[tuple[str, str], int] = {}

    def load(self) -> PetState:
        return self.state

    def save(self, state: PetState) -> None:
        self.state = state

    def daily_count(self, key: str, day: str | None = None) -> int:
        return self.daily.get((day or local_day(), key), 0)

    def bump_daily(self, key: str, day: str | None = None) -> int:
        stamp = day or local_day()
        count = self.daily.get((stamp, key), 0) + 1
        self.daily[(stamp, key)] = count
        return count

    def log_event(self, kind: str, detail: dict | None = None) -> None:
        payload = json.dumps(detail or {}, ensure_ascii=False)
        self.events.append((_iso(datetime.now(timezone.utc)), kind, payload))

    def recent_events(self, limit: int = 20) -> list[tuple[str, str, str]]:
        return list(reversed(self.events[-limit:]))

    def prune_events(self, keep: int = 500) -> int:
        dropped = max(0, len(self.events) - keep)
        if dropped:
            self.events = self.events[-keep:]
        return dropped

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        return self.settings.get(key, default)

    def set_setting(self, key: str, value: str) -> None:
        self.settings[key] = value
