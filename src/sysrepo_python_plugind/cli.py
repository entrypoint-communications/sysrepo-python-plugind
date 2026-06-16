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
    """Parse CLI arguments and run the sysrepo Python plugin daemon.

    Parses ``-d``, ``-v``, ``-p``, and ``-f`` flags (mirroring the C
    sysrepo-plugind), configures logging, creates a PluginDaemon, and
    either daemonizes or runs in the foreground.

    Returns:
        int: Exit code; 0 on success, 1 on error.
    """
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

    # When running under systemd (Type=notify), NOTIFY_SOCKET is set and the
    # process must stay in the foreground so READY=1 is sent from the tracked
    # main PID.  Daemonizing here would cause systemd to reject the notification
    # from the forked grandchild and fail the service with result 'protocol'.
    under_systemd = bool(os.environ.get("NOTIFY_SOCKET"))
    if not args.debug and not under_systemd:
        _daemonize()
    return daemon.run()


# ------------------------------------------------------------------------------
def _run_with_pid(daemon: PluginDaemon, pid_path: str, debug: bool) -> int:
    """Run the daemon with a PID file, handling lock failure gracefully.

    Opens the PID file lock before daemonizing so that a second invocation
    fails immediately with a clear error message.

    Args:
        daemon (PluginDaemon): Configured daemon instance to run.
        pid_path (str): Filesystem path for the PID file.
        debug (bool): If True, skip daemonization and stay in foreground.

    Returns:
        int: Exit code from daemon.run(), or 1 if the PID file is already
            locked by another instance.
    """
    under_systemd = bool(os.environ.get("NOTIFY_SOCKET"))
    try:
        with PidFile(pid_path) as pid_file:
            if not debug and not under_systemd:
                _daemonize()
            return daemon.run(pid_file)
    except RuntimeError as exc:
        # PID file lock failure — another instance is running.
        logging.getLogger(__name__).error("%s", exc)
        return 1


def _configure_logging(debug: bool, level: int) -> None:
    """Configure Python and sysrepo logging.

    In debug mode logs to stderr; otherwise routes to syslog under the
    application name ``'sysrepo-python-plugind'``.

    Args:
        debug (bool): If True, log to stderr; otherwise log to syslog.
        level (int): Python logging level (e.g. ``logging.INFO``).
    """
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
    """Daemonize the current process using the standard double-fork technique.

    After the second fork the process is in its own session, has no
    controlling terminal, and has stdin/stdout/stderr redirected to
    /dev/null.  File descriptors beyond stderr are left open so that a
    PidFile lock opened before this call survives in the child process.
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
