"""The sound layer: keys are closed, the default player records instead of beeps."""

from __future__ import annotations

from betty_pet.audio import SOUND_KEYS, SilentPlayer, sound_for_group, sound_for_refusal


def test_silent_player_records_instead_of_playing():
    player = SilentPlayer()
    player.play("click")
    player.play("feed")
    assert player.history == ["click", "feed"]
    assert player.last == "feed"


def test_silent_player_caps_history():
    player = SilentPlayer(max_history=3)
    for key in ("click", "wave", "feed", "play"):
        player.play(key)
    assert player.history == ["wave", "feed", "play"]


def test_silent_player_clear():
    player = SilentPlayer()
    player.play("click")
    player.clear()
    assert player.history == []
    assert player.last is None


def test_group_keys_are_real_keys():
    for group in ("feed", "play", "rest"):
        key = sound_for_group(group)
        assert key is not None and key in SOUND_KEYS


def test_unknown_group_has_no_sound():
    assert sound_for_group("nonsense") is None
    assert sound_for_group(None) is None


def test_refusal_sound_is_a_real_key():
    assert sound_for_refusal() in SOUND_KEYS


# -- winsound backend -------------------------------------------------------


class _FakeWinsound:
    """Records PlaySound calls so tests can assert what *would* beep."""

    calls: list[str] = []


def _install_fake_winsound(monkeypatch):
    import sys
    import types

    fake = types.ModuleType("winsound")
    fake.SND_ASYNC = 0x0001
    fake.SND_NODEFAULT = 0x0002
    fake.PlaySound = lambda *args: _FakeWinsound.calls.append(args)
    monkeypatch.setitem(sys.modules, "winsound", fake)


def test_winsound_player_plays_the_keyed_file(tmp_path, monkeypatch):
    _install_fake_winsound(monkeypatch)
    _FakeWinsound.calls.clear()
    (tmp_path / "click.wav").write_bytes(b"RIFF")
    from betty_pet.audio import WinsoundPlayer

    player = WinsoundPlayer(tmp_path)
    player.play("click")
    assert len(_FakeWinsound.calls) == 1
    assert _FakeWinsound.calls[0][0].endswith("click.wav")


def test_winsound_player_skips_missing_files(tmp_path, monkeypatch):
    _install_fake_winsound(monkeypatch)
    _FakeWinsound.calls.clear()
    from betty_pet.audio import WinsoundPlayer

    WinsoundPlayer(tmp_path).play("nope")  # must not raise, must not play
    assert _FakeWinsound.calls == []


def test_make_sound_player_prefers_winsound_when_available(tmp_path, monkeypatch):
    _install_fake_winsound(monkeypatch)
    from betty_pet.audio import WinsoundPlayer, make_sound_player

    assert isinstance(make_sound_player(tmp_path), WinsoundPlayer)


def test_make_sound_player_falls_back_to_silent_without_winsound(tmp_path, monkeypatch):
    import sys
    from betty_pet.audio import SilentPlayer, make_sound_player

    monkeypatch.setitem(sys.modules, "winsound", None)  # forces ImportError
    assert isinstance(make_sound_player(tmp_path), SilentPlayer)
