from betty_pet.config import AppConfig


def test_scale_is_clamped_and_rounded() -> None:
    config = AppConfig(min_scale=0.5, max_scale=2.0)
    assert config.clamp_scale(0.1) == 0.5
    assert config.clamp_scale(2.9) == 2.0
    assert config.clamp_scale(1.236) == 1.24

