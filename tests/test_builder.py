from kbuild.builder import extract_device_name, resolve_defconfigs


def test_extract_device_name():
    assert (
        extract_device_name(["vendor/mt6768_defconfig", "vendor/selene.config"])
        == "selene"
    )
    assert extract_device_name(["vendor/mt6768_defconfig"]) == "mt6768"
    assert extract_device_name(["arch/arm64/configs/rosemary_defconfig"]) == "rosemary"
    assert extract_device_name([]) == "generic"


def test_resolve_defconfigs(tmp_path):
    configs_dir = tmp_path / "arch" / "arm64" / "configs"
    vendor_dir = configs_dir / "vendor"
    vendor_dir.mkdir(parents=True)

    (vendor_dir / "mt6768_defconfig").write_text("", encoding="utf-8")
    (vendor_dir / "selene.config").write_text("", encoding="utf-8")

    res = resolve_defconfigs(tmp_path, ["selene"])
    assert res == ["vendor/mt6768_defconfig", "vendor/selene.config"]

    res_direct = resolve_defconfigs(tmp_path, ["vendor/mt6768_defconfig"])
    assert res_direct == ["vendor/mt6768_defconfig"]


def test_builder_positional_path_and_device(tmp_path, monkeypatch):
    import argparse

    from kbuild.builder import KernelBuilder

    (tmp_path / "Makefile").write_text(
        "VERSION = 6\nPATCHLEVEL = 6\n", encoding="utf-8"
    )
    configs_dir = tmp_path / "arch" / "arm64" / "configs" / "vendor"
    configs_dir.mkdir(parents=True)
    (configs_dir / "mt6768_defconfig").write_text("", encoding="utf-8")
    (configs_dir / "selene.config").write_text("", encoding="utf-8")

    parsed_flags = argparse.Namespace(
        clean=None,
        ksu=None,
        ksu_target=None,
        nomount=None,
        nomount_target=None,
        telegram=False,
        gofile=False,
        jobs=4,
        cc=None,
        prefix=None,
        ak3=None,
        clang=None,
        cleanup=False,
    )

    builder = KernelBuilder(parsed_flags, [str(tmp_path), "selene"])
    assert builder.source_dir == tmp_path
    assert builder.defconfigs == ["vendor/mt6768_defconfig", "vendor/selene.config"]
    assert builder.device == "selene"


def test_get_linux_version_full_name(tmp_path):
    import argparse

    from kbuild.builder import KernelBuilder

    (tmp_path / "Makefile").write_text(
        "VERSION = 4\nPATCHLEVEL = 19\nSUBLEVEL = 325\nEXTRAVERSION = -cip20-st20\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True)
    (out_dir / ".config").write_text(
        'CONFIG_LOCALVERSION="-Skyron"\n', encoding="utf-8"
    )

    parsed_flags = argparse.Namespace(
        clean=None,
        ksu=None,
        ksu_target=None,
        nomount=None,
        nomount_target=None,
        telegram=False,
        gofile=False,
        jobs=4,
        cc=None,
        prefix=None,
        ak3=None,
        clang=None,
        cleanup=False,
    )

    builder = KernelBuilder(parsed_flags, [str(tmp_path), "generic"])
    full_ver = builder._get_linux_version(out_dir=out_dir)
    assert full_ver == "4.19.325-cip20-st20-Skyron"


def test_build_started_message_escapes_html_like_values(monkeypatch):
    import argparse
    from unittest.mock import Mock

    from kbuild.builder import KernelBuilder

    builder = object.__new__(KernelBuilder)
    builder.telegram_enabled = True
    builder.telegram = Mock(is_configured=True)
    builder.config = argparse.Namespace(host="builder-host", ksu_setup=None)
    builder.ksu_enabled = False
    builder.nomount_enabled = False
    builder.build_hash = "abc123"
    builder.device = "selene"
    builder.linux_version = "4.19.325-cip20-st20-Skyron"
    builder.compiler_ver = "clang <vrdons>"
    builder.jobs = 4

    monkeypatch.setattr("kbuild.builder.socket.gethostname", lambda: "ignored")
    builder._notify_build_started()

    message = builder.telegram.send_message.call_args.args[0]
    assert "clang &lt;vrdons&gt;" in message
