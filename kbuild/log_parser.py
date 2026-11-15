"""
Kernel build log parser for kbuild.
Extracts relevant compiler, linker, and Kbuild errors while suppressing false positives
and formatting context lines for failure reporting.
"""

from __future__ import annotations

import pathlib
import re

# Clang, GCC, LLD and Kbuild error patterns
ERROR_PATTERNS = re.compile(
    r"(?:"
    r"^.*:\d+:\d+:\s+(?:fatal\s+)?error:.*|"  # Clang/GCC C/C++ errors (file.c:12:5: error: ...)
    r"^ld\.lld:\s+error:.*|"  # LLD linker errors
    r"^.*:\s+undefined reference to\s+.*|"  # Classic linker missing symbol error
    r"^make(?:\[\d+\])?:\s+\*\*\*\s+\[.*\]\s+Error\s+\d+|"  # Make target failure
    r"^scripts/Makefile\..*:\d+:\s+.*|"  # Kbuild Makefile errors
    r"^ERROR:\s+modpost:.*"  # Kernel module (modpost) errors
    r")",
    re.IGNORECASE,
)

# False positive filter (e.g. -Wno-error, 0 errors generated, object files named error.o)
IGNORE_PATTERNS = re.compile(
    r"(?:"
    r"\s+CC\s+.*error.*\.o|"
    r"\s+LD\s+.*error.*\.o|"
    r"-Wno-error|"
    r"0 errors generated"
    r")"
)


def extract_build_errors(
    log_path: pathlib.Path, context_lines: int = 3, max_chars: int = 3500
) -> str:
    """Scans the build log, extracting true compiler/linker errors and adjacent

    context lines while respecting Telegram message size limits.
    """
    if not log_path.is_file():
        return "Log dosyası bulunamadı."

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    matched_indices: set[int] = set()

    for idx, line in enumerate(lines):
        if IGNORE_PATTERNS.search(line):
            continue
        if ERROR_PATTERNS.search(line):
            # Take 1 line before and context_lines lines after (including code indicator ^~~~)
            start = max(0, idx - 1)
            end = min(len(lines), idx + context_lines + 1)
            matched_indices.update(range(start, end))

    if not matched_indices:
        # Fallback to last 25 lines if no specific error pattern matches
        return "\n".join(lines[-25:])

    # Group contiguous lines, insert '...' at breaks
    sorted_idx = sorted(matched_indices)
    output_lines: list[str] = []
    prev: int | None = None

    for idx in sorted_idx:
        if prev is not None and idx > prev + 1:
            output_lines.append("...")
        output_lines.append(lines[idx])
        prev = idx

    result = "\n".join(output_lines)

    # Trim to fit within Telegram message limits, keeping newest/most critical errors
    if len(result) > max_chars:
        result = "...\n" + result[-max_chars:]

    return result
