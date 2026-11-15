from kbuild.log_parser import extract_build_errors


def test_extract_build_errors_missing_file(tmp_path):
    missing = tmp_path / "non_existent.log"
    assert extract_build_errors(missing) == "Log dosyası bulunamadı."


def test_extract_build_errors_fallback(tmp_path):
    log_file = tmp_path / "clean_build.log"
    content = "\n".join(f"Line {i}" for i in range(1, 40))
    log_file.write_text(content, encoding="utf-8")

    result = extract_build_errors(log_file)
    # Should fallback to last 25 lines
    expected = "\n".join(f"Line {i}" for i in range(15, 40))
    assert result == expected


def test_extract_build_errors_clang_error(tmp_path):
    log_file = tmp_path / "clang_err.log"
    lines = [
        "  CC      init/main.o",
        "  CC      drivers/misc/example.o",
        "drivers/misc/example.c:42:15: error: expected ';' after expression",
        "    int a = 10",
        "              ^",
        "              ;",
        "  CC      kernel/fork.o",
        "make[1]: *** [scripts/Makefile.build:280: drivers/misc/example.o] Error 1",
        "make: *** [Makefile:1820: drivers/misc] Error 2",
    ]
    log_file.write_text("\n".join(lines), encoding="utf-8")

    result = extract_build_errors(log_file)
    assert "drivers/misc/example.c:42:15: error:" in result
    assert "int a = 10" in result
    assert "CC      drivers/misc/example.o" in result  # 1 line before


def test_extract_build_errors_lld_and_undefined_ref(tmp_path):
    log_file = tmp_path / "lld_err.log"
    lines = [
        "  LD      vmlinux.o",
        "ld.lld: error: undefined symbol: custom_kernel_function",
        ">>> referenced by core.c:123",
        ">>>               arch/arm64/kernel/core.o:(setup_arch)",
        "drivers/char/random.o: undefined reference to custom_entropy_pool",
    ]
    log_file.write_text("\n".join(lines), encoding="utf-8")

    result = extract_build_errors(log_file)
    assert "ld.lld: error:" in result
    assert "undefined reference to custom_entropy_pool" in result


def test_extract_build_errors_ignore_false_positives(tmp_path):
    log_file = tmp_path / "ignore.log"
    lines = [
        "  CC      drivers/base/error.o",
        "  LD      drivers/base/error.o",
        "clang -Wno-error=unused-variable -c foo.c",
        "0 errors generated.",
        "Compilation succeeded.",
    ]
    log_file.write_text("\n".join(lines), encoding="utf-8")

    result = extract_build_errors(log_file)
    # None matched, should fallback to last 25 lines
    assert result == "\n".join(lines)


def test_extract_build_errors_max_chars(tmp_path):
    log_file = tmp_path / "huge_err.log"
    lines = ["drivers/huge.c:1:1: error: something broke" + ("x" * 100)] * 50
    log_file.write_text("\n".join(lines), encoding="utf-8")

    result = extract_build_errors(log_file, max_chars=300)
    assert len(result) <= 305
    assert result.startswith("...\n")
