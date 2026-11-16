#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# =============================================================================
#  Standalone Zyte kernel build script
#  Device : Redmi 10 Prime (selene) - MediaTek MT6768
#  Kernel : 4.19 (LineageOS 24.0 tree)
#
#  Self-contained bash alternative to the `kb` CLI. It expects a kernel
#  workspace containing source/, toolchains/neutron-clang and an AnyKernel3
#  template. See "Standalone Bash Builder" in README.md.
# =============================================================================
set -Eeuo pipefail

# Run from the workspace root (the directory holding source/), or set
# KBUILD_WORKSPACE. Fall back to the script's own directory so a copy placed
# at the workspace root keeps working when invoked from elsewhere.
if [[ -n "${KBUILD_WORKSPACE:-}" ]]; then
    ROOT="$KBUILD_WORKSPACE"
elif [[ -f "$PWD/source/Makefile" ]]; then
    ROOT="$PWD"
else
    ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
fi

SRC="$ROOT/source"
OUT="$ROOT/out"
AK3="${AK3_DIR:-$ROOT/Zyte-Kernel}"
TC="${CLANG_DIR:-$ROOT/toolchains/neutron-clang}"
ZIP_PREFIX="${ZIP_PREFIX:-Zyte-Kernel}"
LOG="$OUT/build.log"

ARCH="arm64"
DEFCONFIG="vendor/mt6768_defconfig"
FRAGMENT_REL="vendor/selene.config"
FRAGMENT="$SRC/arch/arm64/configs/$FRAGMENT_REL"
JOBS="$(nproc 2>/dev/null || echo 4)"

DO_CLEAN=0
DO_RECONFIG=0
DO_MENUCONFIG=0
DO_ZIP=1
VERBOSE=0

BUILD_PID=""
STAGE_DIR=""
EXTRACT_CERT_CFLAGS=""
TOTAL_START="$(date +%s)"

# -----------------------------------------------------------------------------
# Colours
# -----------------------------------------------------------------------------
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    R=$'\e[0m'
    B=$'\e[1m'
    D=$'\e[2m'
    RED=$'\e[38;5;203m'
    GRN=$'\e[38;5;114m'
    YEL=$'\e[38;5;221m'
    BLU=$'\e[38;5;75m'
    MAG=$'\e[38;5;177m'
    CYN=$'\e[38;5;81m'
    GRY=$'\e[38;5;244m'
else
    R="" B="" D="" RED="" GRN="" YEL="" BLU="" MAG="" CYN="" GRY=""
fi

# -----------------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------------
banner() {
    printf '\n'
    printf '  %s%s%s\n' "$CYN$B" '  ______      _       _  __                    _' "$R"
    printf '  %s%s%s\n' "$CYN$B" ' |___  /     | |     | |/ /                   | |' "$R"
    printf '  %s%s%s\n' "$CYN$B" '    / / _   _| |_ ___| '"'"' / ___ _ __ _ __   ___| |' "$R"
    printf '  %s%s%s\n' "$CYN$B" '   / / | | | | __/ _ \  < / _ \ '"'"'__| '"'"'_ \ / _ \ |' "$R"
    printf '  %s%s%s\n' "$CYN$B" '  / /__| |_| | ||  __/ . \  __/ |  | | | |  __/ |' "$R"
    printf '  %s%s%s\n' "$CYN$B" ' /_____|__, |\__\___|_|\_ \___|_|  |_| |_|\___|_|' "$R"
    printf '  %s%s%s\n' "$CYN$B" '         __/ |' "$R"
    printf '  %s%s%s\n' "$CYN$B" '        |___/' "$R"
    printf '  %sRedmi 10 Prime (selene)  ·  MediaTek MT6768  ·  Linux 4.19%s\n' "$GRY" "$R"
    printf '\n'
}

section() {
    printf '\n  %s%s%s\n' "$B$CYN" "$*" "$R"
    printf '  %s%s%s\n' "$GRY" "$(printf '─%.0s' {1..68})" "$R"
}

row() {
    printf '  %s%-12s%s %s\n' "$GRY" "$1" "$R" "$2"
}

info() { printf '  %s▸%s %s\n' "$BLU" "$R" "$*"; }
ok()   { printf '  %s✔%s %s\n' "$GRN" "$R" "$*"; }
warn() { printf '  %s!%s %s\n' "$YEL" "$R" "$*"; }
bad()  { printf '  %s✘%s %s\n' "$RED" "$R" "$*"; }

die() {
    bad "$*"
    printf '\n'
    exit 1
}

cleanup() {
    if [[ -n "$BUILD_PID" ]] && kill -0 "$BUILD_PID" 2>/dev/null; then
        kill "$BUILD_PID" 2>/dev/null || true
    fi
    if [[ -n "$STAGE_DIR" && -d "$STAGE_DIR" ]]; then
        rm -rf "$STAGE_DIR"
    fi
}

on_interrupt() {
    printf '\r\033[2K'
    printf '\n'
    bad "Build interrupted"
    cleanup
    exit 130
}

trap on_interrupt INT TERM
trap cleanup EXIT

# -----------------------------------------------------------------------------
# Small utilities
# -----------------------------------------------------------------------------
relpath() {
    local p="$1"
    printf '%s' "${p#"$ROOT"/}"
}

human_size() {
    local bytes="$1"
    if (( bytes < 1024 )); then
        printf '%d B' "$bytes"
    else
        numfmt --to=iec-i --suffix=B --format='%.1f' "$bytes"
    fi
}

fmt_duration() {
    local s="$1"
    if (( s >= 3600 )); then
        printf '%dh %02dm %02ds' $((s / 3600)) $(((s % 3600) / 60)) $((s % 60))
    elif (( s >= 60 )); then
        printf '%dm %02ds' $((s / 60)) $((s % 60))
    else
        printf '%ds' "$s"
    fi
}

center() {
    local text="$1" width="$2"
    local len=${#text}
    local left=$(((width - len) / 2))
    local right=$((width - len - left))
    printf '%*s%s%*s' "$left" "" "$text" "$right" ""
}

artifact() {
    local label="$1" path="$2" colour="${3:-$CYN}"
    [[ -e "$path" ]] || return 0
    local size
    size="$(human_size "$(stat -c %s "$path")")"
    printf '  %s%-11s%s %-56s %9s\n' "$colour" "$label" "$R" "$(relpath "$path")" "$size"
}

usage() {
    cat <<EOF

  Zyte Kernel build script - Redmi 10 Prime (selene)

  Usage: ./build.sh [options]

  Options:
    -j, --jobs N       Parallel jobs (default: $(nproc 2>/dev/null || echo 4))
    -c, --clean        Delete out/ and do a clean rebuild
    -r, --reconfig     Regenerate .config from vendor/mt6768_defconfig + vendor/selene.config
    -m, --menuconfig   Open menuconfig before building
        --no-zip       Do not create the AnyKernel3 flashable zip
    -v, --verbose      Stream raw make output instead of the live status line
    -h, --help         Show this help

  Examples:
    ./build.sh                 Incremental build + AnyKernel3 zip
    ./build.sh -c -j8          Clean rebuild with 8 jobs
    ./build.sh -r -m           Regenerate config, tweak it, then build

  Environment:
    KBUILD_WORKSPACE  Workspace root containing source/ (default: current directory)
    AK3_DIR           AnyKernel3 template directory (default: <root>/Zyte-Kernel)
    CLANG_DIR         Clang toolchain directory (default: <root>/toolchains/neutron-clang)
    ZIP_PREFIX        Zip filename prefix (default: Zyte-Kernel)

EOF
}

# -----------------------------------------------------------------------------
# Arguments
# -----------------------------------------------------------------------------
while (($#)); do
    case "$1" in
        -j|--jobs)
            [[ $# -ge 2 ]] || die "$1 needs a value"
            JOBS="$2"
            shift 2
            ;;
        -j*)
            JOBS="${1#-j}"
            shift
            ;;
        -c|--clean)
            DO_CLEAN=1
            shift
            ;;
        -r|--reconfig)
            DO_RECONFIG=1
            shift
            ;;
        -m|--menuconfig)
            DO_MENUCONFIG=1
            shift
            ;;
        --no-zip)
            DO_ZIP=0
            shift
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1 (try --help)"
            ;;
    esac
done

[[ "$JOBS" =~ ^[0-9]+$ ]] && (( JOBS > 0 )) || die "Invalid job count: $JOBS"

# -----------------------------------------------------------------------------
# Pre-flight
# -----------------------------------------------------------------------------
preflight() {
    [[ -f "$SRC/Makefile" ]] || die "Kernel source not found at $SRC (run from the workspace root or set KBUILD_WORKSPACE)"
    [[ -f "$FRAGMENT" ]] || die "Config fragment not found: $FRAGMENT_REL"
    [[ -x "$TC/bin/clang" ]] || die "Toolchain not found at $TC (set CLANG_DIR)"

    export PATH="$TC/bin:$PATH"
    export ARCH="$ARCH"
    export LLVM=1
    export LLVM_IAS=1
    export CROSS_COMPILE="aarch64-linux-gnu-"

    # link-vmlinux.sh bumps .version on every link. Without a fixed value,
    # compile.h changes -> init/version.o rebuilds -> vmlinux.o relinks on
    # every single build, even when nothing else changed.
    export KBUILD_BUILD_VERSION="${KBUILD_BUILD_VERSION:-1}"

    local tool
    for tool in make bc bison flex perl python3 cpio gzip stat numfmt awk df; do
        command -v "$tool" >/dev/null 2>&1 || die "Missing required tool: $tool"
    done
    for tool in clang ld.lld llvm-ar llvm-nm llvm-objcopy llvm-objdump llvm-readelf; do
        command -v "$tool" >/dev/null 2>&1 || die "Missing toolchain tool: $tool"
    done

    if (( DO_ZIP == 1 )); then
        [[ -f "$AK3/anykernel.sh" ]] || die "AnyKernel3 tree not found at $AK3 (set AK3_DIR)"
    fi

    local avail_kb
    avail_kb="$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')"
    if (( avail_kb < 10 * 1024 * 1024 )); then
        warn "Less than 10 GiB free on the build volume"
    fi

    # Modern OpenSSL builds (3.x/4.x) may omit the ENGINE API entirely.
    # Kernel 4.19's extract-cert.c only guards that code for BoringSSL, so
    # compile the PKCS#11 branch out when the host library lacks ENGINE.
    local crypto_lib=""
    crypto_lib="$(ldconfig -p 2>/dev/null | awk '/libcrypto\.so/{lib=$NF} END{print lib}')"
    if [[ -z "$crypto_lib" ]]; then
        crypto_lib="$(pkg-config --variable=libdir libcrypto 2>/dev/null || true)/libcrypto.so"
    fi
    if [[ -e "$crypto_lib" ]] && ! llvm-nm -D "$crypto_lib" 2>/dev/null \
        | grep -w 'ENGINE_load_builtin_engines' >/dev/null; then
        EXTRACT_CERT_CFLAGS="$(pkg-config --cflags libcrypto 2>/dev/null || true) -DOPENSSL_IS_BORINGSSL"
        EXTRACT_CERT_CFLAGS="${EXTRACT_CERT_CFLAGS# }"
        info "OpenSSL without ENGINE detected - applying extract-cert compatibility"
    fi
}

git_meta() {
    GIT_BRANCH="$(git -C "$SRC" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    GIT_COMMIT="$(git -C "$SRC" rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
    GIT_DIRTY=""
    if [[ -n "$(git -C "$SRC" status --porcelain 2>/dev/null)" ]]; then
        GIT_DIRTY=" (dirty)"
    fi
}

compiler_meta() {
    local line version vendor=""
    line="$("$TC/bin/clang" --version | head -n1)"
    version="$(sed -n 's/.*clang version \([^ ]*\).*/\1/p' <<<"$line")"
    [[ "$line" == Neutron* ]] && vendor="Neutron "
    COMPILER="${vendor}clang ${version:-unknown} + LLD"
}

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
kconfig() {
    make -s -C "$SRC" O="$OUT" ARCH="$ARCH" "$@"
}

configure_kernel() {
    section "Configuration"

    if (( DO_RECONFIG == 1 )) || [[ ! -s "$OUT/.config" ]]; then
        info "Generating .config from $DEFCONFIG"
        kconfig "$DEFCONFIG" >>"$LOG" 2>&1 || build_failed "Failed to generate base config"

        info "Merging fragment $FRAGMENT_REL"
        (
            cd "$OUT"
            sh "$SRC/scripts/kconfig/merge_config.sh" -m -O "$OUT" "$OUT/.config" "$FRAGMENT"
        ) >>"$LOG" 2>&1 || build_failed "Failed to merge configuration fragment"

        kconfig olddefconfig >>"$LOG" 2>&1 || build_failed "olddefconfig failed"

        grep -q '^CONFIG_TARGET_PRODUCT_SELENE=y' "$OUT/.config" \
            || die "selene fragment did not apply correctly"
        ok "Config generated from $DEFCONFIG + $FRAGMENT_REL"
    else
        info "Reusing existing out/.config"
        ok "Config unchanged (use -r to regenerate)"
    fi

    if (( DO_MENUCONFIG == 1 )); then
        info "Opening menuconfig"
        make -C "$SRC" O="$OUT" ARCH="$ARCH" menuconfig
        ok "menuconfig finished"
    fi
}

# -----------------------------------------------------------------------------
# Compilation
# -----------------------------------------------------------------------------
compile_kernel() {
    section "Compilation"
    info "Building Image.gz-dtb with -j$JOBS"
    printf '  %sFull log: %s%s\n' "$GRY" "$(relpath "$LOG")" "$R"

    local make_cmd=(make -C "$SRC" O="$OUT" ARCH="$ARCH" -j"$JOBS")
    if [[ -n "$EXTRACT_CERT_CFLAGS" ]]; then
        make_cmd+=("HOSTCFLAGS_extract-cert.o=$EXTRACT_CERT_CFLAGS")
    fi
    make_cmd+=(Image.gz-dtb)

    local start now elapsed i=0 last
    local -a spin=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)
    start="$(date +%s)"

    if (( VERBOSE == 1 )); then
        if ! "${make_cmd[@]}" 2>&1 | tee -a "$LOG"; then
            build_failed "Compilation failed"
        fi
    elif [[ ! -t 1 ]]; then
        # Non-interactive (CI / captured output): keep the log clean.
        if ! "${make_cmd[@]}" >>"$LOG" 2>&1; then
            build_failed "Compilation failed"
        fi
    else
        "${make_cmd[@]}" >>"$LOG" 2>&1 &
        BUILD_PID=$!

        while kill -0 "$BUILD_PID" 2>/dev/null; do
            now="$(date +%s)"
            elapsed=$((now - start))
            last="$(tail -n 8 "$LOG" 2>/dev/null | tr -d '\r' \
                | sed -n 's/^  \([A-Z][A-Z]*\)[[:space:]]\+/\1 /p' | tail -n1)"
            [[ -n "$last" ]] || last="working..."
            last="${last:0:58}"
            printf '\r\033[2K  %s%s%s %s  %s%s%s' \
                "$CYN" "${spin[i]}" "$R" "$(fmt_duration "$elapsed")" "$GRY" "$last" "$R"
            i=$(((i + 1) % 10))
            sleep 0.15
        done

        set +e
        wait "$BUILD_PID"
        local rc=$?
        set -e
        BUILD_PID=""
        printf '\r\033[2K'

        if (( rc != 0 )); then
            build_failed "Compilation failed"
        fi
    fi

    COMPILE_SECONDS=$(($(date +%s) - start))
    ok "Kernel compiled in $(fmt_duration "$COMPILE_SECONDS")"
}

# -----------------------------------------------------------------------------
# Artifact verification
# -----------------------------------------------------------------------------
KERNEL_IMAGE="$OUT/arch/arm64/boot/Image.gz-dtb"
DTB="$OUT/arch/arm64/boot/dts/mediatek/mt6768.dtb"
DTBO="$OUT/arch/arm64/boot/dts/mediatek/selene.dtbo"

verify_artifacts() {
    local f
    for f in "$KERNEL_IMAGE" "$DTB" "$DTBO"; do
        [[ -s "$f" ]] || build_failed "Expected artifact missing or empty: $(relpath "$f")"
    done
}

resolve_release() {
    KERNEL_RELEASE="$(cat "$OUT/include/config/kernel.release" 2>/dev/null || true)"
    if [[ -z "$KERNEL_RELEASE" ]]; then
        KERNEL_RELEASE="$(make -s -C "$SRC" O="$OUT" ARCH="$ARCH" kernelrelease 2>>"$LOG" | tail -n1)"
    fi
    [[ -n "$KERNEL_RELEASE" ]] || die "Could not determine kernel release"
}

# MediaTek's eccci Makefile does `obj-y += $(CONFIG_MTK_PLATFORM)/` while the
# Kconfig value contains quotes ("mt6768"). The shell strips them when running
# ar, but Kbuild's prerequisite list keeps the literal quotes and therefore
# always sees a missing input, rebuilding this archive -> drivers -> vmlinux.o
# -> LTO on every single build. Satisfy that phantom dependency with a symlink
# so incremental builds are actually incremental.
fix_mtk_quoted_platform() {
    local platform quoted
    platform="$(sed -n 's/^CONFIG_MTK_PLATFORM="\([^"]*\)"/\1/p' "$OUT/.config" | head -n1)"
    [[ -n "$platform" ]] || return 0

    quoted="$OUT/drivers/misc/mediatek/eccci/\"$platform\""
    mkdir -p "$quoted"
    ln -sfn "../$platform/built-in.a" "$quoted/built-in.a"
}

# -----------------------------------------------------------------------------
# AnyKernel3 packaging
# -----------------------------------------------------------------------------
ZIP=""

package_anykernel() {
    (( DO_ZIP == 1 )) || return 0

    section "AnyKernel3 package"
    info "Staging kernel + AnyKernel3"

    STAGE_DIR="$(mktemp -d "$OUT/.ak3-stage.XXXXXX")"
    cp -a "$AK3/." "$STAGE_DIR/"
    cp -f "$KERNEL_IMAGE" "$STAGE_DIR/Image.gz-dtb"
    cp -f "$DTB" "$STAGE_DIR/dtb"

    local stamp base
    stamp="$(date +%Y%m%d-%H%M)"
    base="${KERNEL_RELEASE%-ZyteKernel}"
    ZIP="$OUT/${ZIP_PREFIX}-${base}-${stamp}.zip"
    rm -f "$ZIP"

    if command -v zip >/dev/null 2>&1; then
        (cd "$STAGE_DIR" && zip -qr9 "$ZIP" .) >>"$LOG" 2>&1 \
            || build_failed "Failed to create AnyKernel3 zip"
    else
        python3 - "$STAGE_DIR" "$ZIP" <<'PY' >>"$LOG" 2>&1 || build_failed "Failed to create AnyKernel3 zip"
import os
import sys
import zipfile

stage, output = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for root, dirs, files in os.walk(stage):
        dirs.sort()
        files.sort()
        for name in files:
            full = os.path.join(root, name)
            zf.write(full, os.path.relpath(full, stage))
PY
    fi

    python3 - "$ZIP" <<'PY' >>"$LOG" 2>&1 || build_failed "AnyKernel3 zip validation failed"
import sys
import zipfile

zf = zipfile.ZipFile(sys.argv[1])
names = set(zf.namelist())
required = {
    "anykernel.sh",
    "Image.gz-dtb",
    "dtb",
    "META-INF/com/google/android/update-binary",
    "tools/ak3-core.sh",
}
missing = required - names
if missing:
    raise SystemExit("missing from zip: " + ", ".join(sorted(missing)))
for item in ("anykernel.sh", "META-INF/com/google/android/update-binary"):
    mode = (zf.getinfo(item).external_attr >> 16) & 0o777
    if not mode & 0o111:
        raise SystemExit(f"{item} is not executable in zip (mode {mode:o})")
PY

    rm -rf "$STAGE_DIR"
    STAGE_DIR=""
    ok "Packaged $(basename "$ZIP")"
}

# -----------------------------------------------------------------------------
# Failure / success screens
# -----------------------------------------------------------------------------
build_failed() {
    local title="$1"
    cleanup
    printf '\r\033[2K'
    printf '\n'
    bad "$title"
    printf '\n'

    local errors
    errors="$(grep -nE 'error:|Error [0-9]+|undefined reference|No rule to make target|fatal error' \
        "$LOG" 2>/dev/null | tail -n 12 || true)"
    if [[ -n "$errors" ]]; then
        printf '  %sErrors%s\n' "$B$RED" "$R"
        printf '%s\n' "$errors" | sed 's/^/    /'
        printf '\n'
    fi

    printf '  %sLast lines of the log%s\n' "$B$YEL" "$R"
    tail -n 25 "$LOG" 2>/dev/null | sed 's/^/    /'
    printf '\n  %sFull log:%s %s\n\n' "$GRY" "$R" "$(relpath "$LOG")"
    exit 1
}

success_screen() {
    local total hr
    total=$(($(date +%s) - TOTAL_START))
    hr="$(printf '─%.0s' {1..60})"

    section "Build complete"
    printf '  %s╭%s╮%s\n' "$GRN" "$hr" "$R"
    printf '  %s│%s%s%s│%s\n' "$GRN" "$R" "$(center "BUILD SUCCESSFUL" 60)" "$GRN" "$R"
    printf '  %s│%s%s%s│%s\n' "$GRN" "$R" "$(center "$KERNEL_RELEASE" 60)" "$GRN" "$R"
    printf '  %s╰%s╯%s\n' "$GRN" "$hr" "$R"
    printf '\n'

    row "Device" "Redmi 10 Prime (selene) · MT6768"
    row "Source" "$GIT_BRANCH @ $GIT_COMMIT$GIT_DIRTY"
    row "Compiler" "$COMPILER"
    row "Build time" "$(fmt_duration "$total")"
    row "Jobs" "$JOBS"

    section "Artifacts"
    artifact "Kernel" "$KERNEL_IMAGE" "$GRN$B"
    artifact "DTB" "$DTB"
    artifact "DTBO" "$DTBO"
    artifact "Image" "$OUT/arch/arm64/boot/Image"
    artifact "vmlinux" "$OUT/vmlinux"
    artifact "System.map" "$OUT/System.map"
    artifact "Config" "$OUT/.config"
    if [[ -n "$ZIP" ]]; then
        artifact "AnyKernel" "$ZIP" "$MAG"
    fi
    printf '  %s%-11s%s %s\n' "$GRY" "Log" "$R" "$(relpath "$LOG")"

    printf '\n  %sKernel + DTB + DTBO are appended in Image.gz-dtb.%s\n' "$GRY" "$R"
    if [[ -n "$ZIP" ]]; then
        printf '  %sZip contains Image.gz-dtb + standalone dtb (mt6768).%s\n' "$GRY" "$R"
        printf '  %sFlash the AnyKernel3 zip in recovery, or use Image.gz-dtb directly.%s\n' "$GRY" "$R"
    fi
    printf '\n'
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
banner
preflight
git_meta
compiler_meta

section "Build configuration"
row "Target" "Redmi 10 Prime (selene) · MT6768"
row "Source" "$GIT_BRANCH @ $GIT_COMMIT$GIT_DIRTY"
row "Config" "$DEFCONFIG + $FRAGMENT_REL"
row "Toolchain" "$COMPILER"
row "Output" "out/"
row "Jobs" "$JOBS"

if (( DO_CLEAN == 1 )); then
    section "Clean"
    info "Removing out/"
    rm -rf "$OUT"
    ok "Clean"
fi

mkdir -p "$OUT"
{
    printf 'Zyte Kernel build log\n'
    printf 'Started : %s\n' "$(date -Is)"
    printf 'Target  : Image.gz-dtb (selene)\n'
    printf 'Config  : %s + %s\n' "$DEFCONFIG" "$FRAGMENT_REL"
    printf 'Compiler: %s\n\n' "$COMPILER"
} >"$LOG"

configure_kernel
fix_mtk_quoted_platform
compile_kernel
verify_artifacts
resolve_release
package_anykernel
success_screen
