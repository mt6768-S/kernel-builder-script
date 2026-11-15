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
