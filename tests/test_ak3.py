import pathlib
import zipfile

from kbuild.ak3 import AnyKernelManager
from kbuild.config import KbuildConfig


def test_ak3_package(tmp_path, monkeypatch):
    ak3_dir = tmp_path / "ak3_cache"
    ak3_dir.mkdir()
    (ak3_dir / "anykernel.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    cfg = KbuildConfig()
    mgr = AnyKernelManager(cfg)
    mgr.ak3_dir = ak3_dir

    fake_kernel = tmp_path / "Image.gz"
    fake_kernel.write_text("KERNEL_DATA", encoding="utf-8")

    zip_path, sha256_hex = mgr.package(
        artifacts=[fake_kernel],
        device="selene",
        prefix="TestZip",
        explicit_ak3=str(ak3_dir),
    )

    assert zip_path.is_file()
    assert zip_path.parent == pathlib.Path("/tmp")
    assert "TestZip-selene-" in zip_path.name
    assert len(sha256_hex) == 64

    # Verify zip content
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "anykernel.sh" in names
        assert "Image.gz" in names

    # Clean up generated test zip in /tmp
    if zip_path.is_file():
        zip_path.unlink()
