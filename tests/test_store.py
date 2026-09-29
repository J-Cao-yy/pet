import sqlite3
from datetime import datetime, timedelta, timezone

from betty_pet.state import PetState, PetStats
from betty_pet.store import MemoryStateStore, SQLiteStateStore, local_day


def test_state_roundtrips_through_sqlite(tmp_path) -> None:
    store = SQLiteStateStore(tmp_path / "pet.db")
    store.save(PetState(PetStats(hunger=42.0, mood=55.0, energy=66.0)))
    loaded = store.load()
    assert (loaded.stats.hunger, loaded.stats.mood, loaded.stats.energy) == (42.0, 55.0, 66.0)


def test_affection_roundtrips_through_sqlite(tmp_path) -> None:
    store = SQLiteStateStore(tmp_path / "pet.db")
    store.save(PetState(affection=137.0))
    assert store.load().affection == 137.0


def test_offline_gap_is_applied_on_reload(tmp_path) -> None:
    store = SQLiteStateStore(tmp_path / "pet.db")
    past = datetime.now(timezone.utc) - timedelta(minutes=10)
    store.save(PetState(PetStats(hunger=20.0, mood=80.0, energy=80.0), last_updated=past))
    loaded = store.load()
    loaded.update_elapsed()
    assert loaded.stats.hunger > 20.0
    assert loaded.stats.energy < 80.0


def test_a_database_from_an_older_version_still_opens(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE pet_state ("
        "id INTEGER PRIMARY KEY CHECK (id = 1), hunger REAL NOT NULL, mood REAL NOT NULL, "
        "energy REAL NOT NULL, last_updated TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO pet_state (id, hunger, mood, energy, last_updated) VALUES (1, 33, 44, 55, ?)",
        (datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),),
    )
    connection.commit()
    connection.close()

    loaded = SQLiteStateStore(db_path).load()
    assert (loaded.stats.hunger, loaded.stats.mood, loaded.stats.energy) == (33.0, 44.0, 55.0)
    assert loaded.affection == 0.0


def test_daily_usage_counts_per_day_and_per_key(tmp_path) -> None:
    store = SQLiteStateStore(tmp_path / "pet.db")
    assert store.daily_count("cookie") == 0
    assert store.bump_daily("cookie") == 1
    assert store.bump_daily("cookie") == 2
    assert store.daily_count("cookie") == 2
    assert store.daily_count("fish") == 0
    assert store.daily_count("cookie", day="2000-01-01") == 0
    assert store.bump_daily("cookie", day="2000-01-01") == 1


def test_daily_usage_survives_reopening(tmp_path) -> None:
    path = tmp_path / "pet.db"
    SQLiteStateStore(path).bump_daily("nap")
    assert SQLiteStateStore(path).daily_count("nap") == 1


def test_local_day_is_a_calendar_date() -> None:
    day = local_day()
    assert len(day) == 10 and day[4] == "-" and day[7] == "-"


def test_settings_roundtrip(tmp_path) -> None:
    store = SQLiteStateStore(tmp_path / "pet.db")
    assert store.get_setting("scale") is None
    store.set_setting("scale", "1.25")
    store.set_setting("scale", "1.50")
    assert store.get_setting("scale") == "1.50"
    assert SQLiteStateStore(tmp_path / "pet.db").get_setting("scale") == "1.50"


def test_event_log_is_newest_first_and_can_be_pruned(tmp_path) -> None:
    store = SQLiteStateStore(tmp_path / "pet.db")
    store.log_event("startup", {})
    store.log_event("item", {"item": "fish"})
    assert [kind for _ts, kind, _detail in store.recent_events(limit=2)] == ["item", "startup"]
    assert store.prune_events(keep=1) == 1
    assert len(store.recent_events()) == 1


def test_memory_store_behaves_the_same() -> None:
    store = MemoryStateStore()
    state = PetState(PetStats(hunger=50.0), affection=20.0)
    store.save(state)
    store.log_event("startup", {})
    store.set_setting("scale", "1.0")
    assert store.load() is state
    assert store.get_setting("scale") == "1.0"
    assert store.recent_events()[0][1] == "startup"
    assert store.prune_events(keep=0) == 1
    assert store.bump_daily("cookie") == 1
    assert store.daily_count("cookie") == 1
    assert store.daily_count("cookie", day="2000-01-01") == 0
