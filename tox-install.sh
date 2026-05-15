#!/bin/bash
# Build libyang and sysrepo C libraries from source, then install Python
# packages.  Used as the tox install_command so environments are
# self-contained and do not require system-installed sysrepo/libyang.
#
# Usage: tox-install.sh WORK_DIR [pip-opts] PACKAGES
#
# Environment variables (all optional):
#   LIBYANG_BRANCH   libyang git branch/tag to build  (default: devel)
#   SYSREPO_BRANCH   sysrepo git branch/tag to build  (default: devel)
#   LIBYANG_DIR      pre-cloned libyang source directory
#   SYSREPO_DIR      pre-cloned sysrepo source directory

set -e

WORK_DIR="$1"
shift

LIBYANG_BRANCH="${LIBYANG_BRANCH:-devel}"
SYSREPO_BRANCH="${SYSREPO_BRANCH:-devel}"

# C libraries are installed here, shared across all tox environments.
PREFIX="${WORK_DIR}/usr"
LIBYANG_SRC="${LIBYANG_DIR:-${WORK_DIR}/libyang}"
SYSREPO_SRC="${SYSREPO_DIR:-${WORK_DIR}/sysrepo}"

# ---------------------------------------------------------------------------
# Download helper: try git, then curl, then wget.
# Skips the clone if the destination directory already exists.
download() {
    local repo="$1" branch="$2" dest="$3"
    [ -d "$dest" ] && return 0
    if command -v git > /dev/null 2>&1; then
        git clone --branch "$branch" --depth 1 "$repo" "$dest"
    elif command -v curl > /dev/null 2>&1; then
        curl -sL "${repo}/archive/refs/heads/${branch}.tar.gz" \
            | tar xz -C "$(dirname "$dest")"
        mv "$(dirname "$dest")/$(basename "$repo")-${branch}" "$dest"
    else
        wget -q -O - "${repo}/archive/refs/heads/${branch}.tar.gz" \
            | tar xz -C "$(dirname "$dest")"
        mv "$(dirname "$dest")/$(basename "$repo")-${branch}" "$dest"
    fi
}

# ---------------------------------------------------------------------------
# Build libyang (skip if already installed)
if [ ! -f "${PREFIX}/lib/libyang.so" ]; then
    download "https://github.com/CESNET/libyang" "$LIBYANG_BRANCH" "$LIBYANG_SRC"
    cmake -S "$LIBYANG_SRC" -B "${LIBYANG_SRC}/build" \
        -DCMAKE_BUILD_TYPE=Debug \
        -DCMAKE_INSTALL_PREFIX="$PREFIX" \
        -DENABLE_TESTS=OFF \
        -DENABLE_FUZZ_TARGETS=OFF
    cmake --build "${LIBYANG_SRC}/build" -j"$(nproc)"
    cmake --install "${LIBYANG_SRC}/build"
fi

# ---------------------------------------------------------------------------
# Build sysrepo (skip if already installed)
if [ ! -f "${PREFIX}/lib/libsysrepo.so" ]; then
    download "https://github.com/sysrepo/sysrepo" "$SYSREPO_BRANCH" "$SYSREPO_SRC"
    cmake -S "$SYSREPO_SRC" -B "${SYSREPO_SRC}/build" \
        -DCMAKE_BUILD_TYPE=Debug \
        -DCMAKE_INSTALL_PREFIX="$PREFIX" \
        -DCMAKE_PREFIX_PATH="$PREFIX" \
        -DENABLE_TESTS=OFF \
        -DENABLE_FUZZ_TARGETS=OFF
    cmake --build "${SYSREPO_SRC}/build" -j"$(nproc)"
    cmake --install "${SYSREPO_SRC}/build"
fi

# ---------------------------------------------------------------------------
# Export paths so sysrepo-python's CFFI compilation finds the headers and
# libraries.  RPATH is embedded in the compiled .so so it finds libyang and
# libsysrepo at runtime without needing LD_LIBRARY_PATH.
export SYSREPO_HEADERS="${PREFIX}/include"
export SYSREPO_LIBRARIES="${PREFIX}/lib"
export SYSREPO_EXTRA_CFLAGS="-I${PREFIX}/include"
export SYSREPO_EXTRA_LDFLAGS="-L${PREFIX}/lib -Wl,-rpath,${PREFIX}/lib -Wl,--enable-new-dtags"

export LIBYANG_HEADERS="${PREFIX}/include"
export LIBYANG_LIBRARIES="${PREFIX}/lib"
export LIBYANG_EXTRA_CFLAGS="-I${PREFIX}/include"
export LIBYANG_EXTRA_LDFLAGS="-L${PREFIX}/lib -Wl,-rpath,${PREFIX}/lib -Wl,--enable-new-dtags"

pip install --no-cache-dir "$@"
