from unittest.mock import MagicMock, patch

import pytest

from kbuild.errors import IntegrationError
from kbuild.ksu import KernelSUManager, extract_ksu_owner
from kbuild.nomount import NoMountManager


def test_extract_ksu_owner():
    assert (
        extract_ksu_owner(
            "https://raw.githubusercontent.com/backslashxx/KernelSU/master/kernel/setup.sh"
        )
        == "backslashxx"
    )
    assert (
        extract_ksu_owner(
            "https://raw.githubusercontent.com/Mrshockwaveog/KernelSU/main/kernel/setup.sh"
        )
        == "Mrshockwaveog"
    )
    assert (
        extract_ksu_owner(
            "https://raw.githubusercontent.com/EmreDemirn/KernelSU/skyron/kernel/setup.sh"
        )
        == "EmreDemirn"
    )
    assert extract_ksu_owner("https://example.com/custom_setup.sh") == "OK"
    assert extract_ksu_owner("") == "OK"


def test_ksu_apply_config(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    config_file = out_dir / ".config"
    config_file.write_text("CONFIG_FOO=y\n# CONFIG_KSU is not set\n", encoding="utf-8")

    mgr = KernelSUManager(tmp_path, "https://example.com/setup.sh", "master")
    mgr._apply_ksu_config(config_file)

    content = config_file.read_text(encoding="utf-8")
    assert "CONFIG_KSU=y" in content
    assert "CONFIG_KSU_EXTRAS=y" in content
    assert "CONFIG_KSU_TAMPER_SYSCALL_TABLE=y" in content
    assert "CONFIG_KSU_THRONE_TRACKER_ALWAYS_THREADED=y" in content


def test_nomount_apply_config(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    config_file = out_dir / ".config"
    config_file.write_text(
        "CONFIG_FOO=y\n# CONFIG_NOMOUNT is not set\n", encoding="utf-8"
    )

    mgr = NoMountManager(tmp_path, "https://example.com/nomount_setup.sh", "dev")
    mgr._apply_nomount_config(config_file)

    content = config_file.read_text(encoding="utf-8")
    assert "CONFIG_NOMOUNT=y" in content


@patch("requests.get")
@patch("subprocess.run")
def test_ksu_inject_failure(mock_subproc, mock_get, tmp_path):
    mock_resp = MagicMock()
    mock_resp.text = "echo test"
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp

    mock_run_res = MagicMock()
    mock_run_res.returncode = 1
    mock_run_res.stdout = "Failed patch"
    mock_run_res.stderr = ""
    mock_subproc.return_value = mock_run_res

    mgr = KernelSUManager(tmp_path, "https://example.com/setup.sh", "master")
    with pytest.raises(IntegrationError):
        mgr.inject()


@patch("requests.get")
@patch("subprocess.run")
def test_nomount_inject_success(mock_subproc, mock_get, tmp_path):
    mock_resp = MagicMock()
    mock_resp.text = "echo test"
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp

    mock_run_res = MagicMock()
    mock_run_res.returncode = 0
    mock_run_res.stdout = "Patched successfully"
    mock_run_res.stderr = ""
    mock_subproc.return_value = mock_run_res

    mgr = NoMountManager(tmp_path, "https://example.com/nomount_setup.sh", "dev")
    mgr.inject()
    assert mgr.injected is True
