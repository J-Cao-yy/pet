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
