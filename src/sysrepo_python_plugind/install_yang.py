# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

"""Install or upgrade the sysrepo-python-plugind YANG module into sysrepo."""

import argparse
import subprocess
import sys
from importlib.resources import as_file, files


_MODULE_NAME = "sysrepo-python-plugind"


def main() -> int:
    """Install or upgrade the sysrepo-python-plugind YANG augmentation module.

    Checks whether the module is already installed via ``sysrepoctl --list``
    and either skips (already installed, no ``--force``), installs (first
    run), or upgrades (``--force``) using ``sysrepoctl``.

    Returns:
        int: 0 on success or when already installed, non-zero if
            ``sysrepoctl`` exits with an error.
    """
    parser = argparse.ArgumentParser(
        prog="sysrepo-python-plugind-setup",
        description="Install the sysrepo-python-plugind YANG augmentation module.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="upgrade the module even if it is already installed",
    )
    args = parser.parse_args()

    already_installed = _is_installed()

    if not args.force and already_installed:
        print(f"{_MODULE_NAME}: already installed, nothing to do")
        print("  (use --force to upgrade)")
        return 0

    flag = "--update" if already_installed else "--install"
    verb = "Upgrading" if already_installed else "Installing"

    yang_ref = files("sysrepo_python_plugind").joinpath(
        "yang/sysrepo-python-plugind.yang"
    )
    with as_file(yang_ref) as yang_path:
        print(f"{verb} {yang_path} ...")
        result = subprocess.run(
            ["sysrepoctl", flag, str(yang_path)],
            check=False,
        )
        if result.returncode != 0:
            print(
                f"sysrepoctl {flag} failed (exit {result.returncode})",
                file=sys.stderr,
            )
            return result.returncode

    print(f"{_MODULE_NAME}: module installed successfully")
    return 0


def _is_installed() -> bool:
    """Check whether the sysrepo-python-plugind YANG module is installed.

    Runs ``sysrepoctl --list`` and searches the output for the module name.

    Returns:
        bool: True if the module appears in ``sysrepoctl`` output, False
            otherwise or if ``sysrepoctl`` itself fails.
    """
    result = subprocess.run(
        ["sysrepoctl", "--list"],
        capture_output=True,
        text=True,
        check=False,
    )
    return _MODULE_NAME in result.stdout
