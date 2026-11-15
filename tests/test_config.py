from kbuild.settings import (
    KbuildConfig,
    load_config,
    save_config,
    update_config_from_pairs,
)


def _patch_config_file(tmp_path, monkeypatch):
    custom_root = tmp_path / ".kbuild"
    monkeypatch.setattr("kbuild.paths.KBUILD_ROOT", custom_root)
    monkeypatch.setattr("kbuild.paths.KBUILD_CONFIG_FILE", custom_root / "config.json")
    return custom_root / "config.json"


def test_default_config():
    cfg = KbuildConfig()
    assert cfg.telegram is True
    assert cfg.gofile is False
    assert cfg.clean is True
    assert cfg.ksu is False
    assert cfg.nomount is False
    assert cfg.ksu_target == "master"
    assert cfg.nomount_target == "dev"
    assert cfg.zip_prefix == "Skyron"
    assert cfg.default_defconfig == "vendor/mt6768_defconfig"
    assert cfg.jobs is None


def test_boolean_coercion(tmp_path, monkeypatch):
    _patch_config_file(tmp_path, monkeypatch)

    updated = update_config_from_pairs(["telegram=no", "gofile=enable"])
    assert updated.telegram is False
    assert updated.gofile is True

    unchanged = update_config_from_pairs(["telegram=invalid"])
    assert unchanged.telegram is False


def test_save_and_load_config(tmp_path, monkeypatch):
    cfg_file = _patch_config_file(tmp_path, monkeypatch)

    cfg = KbuildConfig()
    cfg.zip_prefix = "CustomPrefix"
    cfg.telegram = False
    cfg.jobs = 8
    save_config(cfg)

    assert cfg_file.is_file()
    mode = cfg_file.stat().st_mode & 0o777
    assert mode == 0o600

    loaded = load_config()
    assert loaded.zip_prefix == "CustomPrefix"
    assert loaded.telegram is False
    assert loaded.jobs == 8


def test_update_config_from_pairs(tmp_path, monkeypatch):
    _patch_config_file(tmp_path, monkeypatch)

    updated = update_config_from_pairs(
        ["telegram=false", "ksu=true", "ksu_target=v3.0", "jobs=12"]
    )
    assert updated.telegram is False
    assert updated.ksu is True
    assert updated.ksu_target == "v3.0"
    assert updated.jobs == 12

    reset_cfg = update_config_from_pairs(["reset"])
    assert reset_cfg.telegram is True
    assert reset_cfg.ksu is False
    assert reset_cfg.ksu_target == "master"
    assert reset_cfg.jobs is None
