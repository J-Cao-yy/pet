from pathlib import Path

from betty_pet.assets import AssetCatalog


def test_project_manifest_has_existing_frames() -> None:
    catalog = AssetCatalog(Path(__file__).parents[1] / "assets")
    assert len(catalog.actions()) >= 5
    assert catalog.missing_files() == []


def test_resized_frames_have_no_transparent_color_halo() -> None:
    catalog = AssetCatalog(Path(__file__).parents[1] / "assets")
    alpha_values = set(catalog.load_frames("idle", (128, 128))[0].getchannel("A").getdata())
    assert alpha_values <= {0, 255}
