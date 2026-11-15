from kbuild.cli import parse_build_arguments


def test_dirty_is_no_clean_alias():
    parsed, remaining = parse_build_arguments(["--dirty", "vendor/selene.config"])

    assert parsed.clean is False
    assert remaining == ["vendor/selene.config"]
