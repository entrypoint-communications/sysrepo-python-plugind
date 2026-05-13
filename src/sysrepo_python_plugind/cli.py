# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

import argparse
import logging
import os
import sys
from typing import Optional

import sysrepo

from .daemon import PluginDaemon
from .pid import PidFile

# Map sysrepo-plugind -v levels to Python logging levels, matching the C daemon.
_LOG_LEVELS = {
    0: logging.ERROR,
    1: logging.WARNING,
    2: logging.INFO,
    3: logging.DEBUG,
    4: logging.DEBUG,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="sysrepo-python-plugind",
        description="Sysrepo Python plugin daemon",
    )
    parser.add_argument(
        "-d",
        dest="debug",
        action="store_true",
        help="debug mode: stay in foreground, log to stderr",
    )
    parser.add_argument(
        "-v",
        dest="verbosity",
        type=int,
        default=2,
        metavar="LEVEL",
        choices=range(5),
        help="log verbosity 0-4 (default: 2 = INFO)",
    )
    parser.add_argument(
        "-p",
        dest="pid_file",
        metavar="PATH",
        help="write PID file at PATH",
    )
    parser.add_argument(
        "-f",
        dest="fatal_fail",
        action="store_true",
        help="exit if any plugin fails to initialise",
    )
    args = parser.parse_args()

    log_level = _LOG_LEVELS.get(args.verbosity, logging.DEBUG)
    _configure_logging(debug=args.debug, level=log_level)

    daemon = PluginDaemon(fatal_fail=args.fatal_fail)

    if args.pid_file:
        return _run_with_pid(daemon, args.pid_file, debug=args.debug)

    if not args.debug:
        _daemonize()
    return daemon.run()


# ------------------------------------------------------------------------------
def _run_with_pid(daemon: PluginDaemon, pid_path: str, debug: bool) -> int:
    try:
        with PidFile(pid_path) as pid_file:
            if not debug:
                _daemonize()
            return daemon.run(pid_file)
    except RuntimeError as exc:
        # PID file lock failure — another instance is running.
        logging.getLogger(__name__).error("%s", exc)
        return 1


def _configure_logging(debug: bool, level: int) -> None:
    handler = logging.StreamHandler()
    handler.setLevel(level)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(level)

    if debug:
        sysrepo.configure_logging(stderr_level=level, py_logging=True)
    else:
        sysrepo.configure_logging(
            syslog_level=level,
            syslog_app_name="sysrepo-python-plugind",
            py_logging=True,
        )


def _daemonize() -> None:
    """
    Standard double-fork daemonization.

    File descriptors other than stdin/stdout/stderr are left open so that
    a PidFile opened before this call remains valid in the child.
    """
    # First fork: become session leader's child.
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    os.setsid()

    # Second fork: ensure we can never re-acquire a controlling terminal.
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    os.chdir("/")

    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (sys.stdin.fileno(), sys.stdout.fileno(), sys.stderr.fileno()):
        os.dup2(devnull, fd)
    os.close(devnull)
