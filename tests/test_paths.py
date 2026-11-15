import pathlib

from kbuild.paths import find_local_config, get_kbuild_root


def test_get_kbuild_root_default(monkeypatch):
    monkeypatch.delenv("KBUILD_DIR", raising=False)
    expected = (pathlib.Path.home() / ".kbuild").resolve()
    assert get_kbuild_root() == expected


def test_get_kbuild_root_custom(monkeypatch, tmp_path):
    monkeypatch.setenv("KBUILD_DIR", str(tmp_path))
    assert get_kbuild_root() == tmp_path.resolve()


def test_find_local_config(tmp_path):
    assert find_local_config(tmp_path) is None
    cfg_file = tmp_path / ".kb.json"
    cfg_file.write_text("{}", encoding="utf-8")
    assert find_local_config(tmp_path) == cfg_file
