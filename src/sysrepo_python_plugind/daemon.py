# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

import asyncio
import contextlib
import logging
import os
import signal
import socket
import sys
import threading
from importlib.metadata import entry_points
from typing import Optional

import sysrepo

from .pid import PidFile
from .plugin import SysrepoPlugin
from .sort import PluginList, sort_plugins

LOG = logging.getLogger(__name__)

_LOADED_XPATH = (
    "/sysrepo-plugind:sysrepo-plugind"
    "/sysrepo-python-plugind:python-loaded-plugins/plugin"
)
_LOADED_CONTAINER = (
    "/sysrepo-plugind:sysrepo-plugind"
    "/sysrepo-python-plugind:python-loaded-plugins"
)


class PluginDaemon:
    """
    Python equivalent of sysrepo-plugind.

    Lifecycle::

        daemon = PluginDaemon(fatal_fail=False)
        with PidFile("/run/srpy-plugind.pid") as pid_file:
            _daemonize()
            rc = daemon.run(pid_file)
        sys.exit(rc)
    """

    def __init__(self, fatal_fail: bool = False) -> None:
        self.fatal_fail = fatal_fail
        self._stop = threading.Event()
        self._plugins: PluginList = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public entry point

    def run(self, pid_file: Optional[PidFile] = None) -> int:
        """
        Run the daemon; block until a termination signal is received.

        Returns 0 on clean shutdown, 1 on error.
        """
        self._setup_signals()
        self._start_event_loop()

        rc = 0
        try:
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session("running") as sess:
                    self._init_plugins(sess)
                    self._publish_loaded(sess)
                    if pid_file is not None:
                        pid_file.write()
                    _sd_notify("READY=1")
                    LOG.info(
                        "daemon ready, %d plugin(s) loaded", len(self._plugins)
                    )
                    self._stop.wait()
                    LOG.info("shutting down")
                    _sd_notify("STOPPING=1")
                    self._cleanup_plugins(sess)
        except Exception:
            LOG.exception("daemon error")
            rc = 1
        finally:
            self._stop_event_loop()

        return rc

    # ------------------------------------------------------------------
    # Signal handling

    def _setup_signals(self) -> None:
        def _handler(sig: int, _frame) -> None:
            if self._stop.is_set():
                # Second signal while already shutting down → hard exit.
                sys.exit(1)
            LOG.info("received %s, initiating shutdown", signal.Signals(sig).name)
            self._stop.set()

        for sig in (
            signal.SIGINT,
            signal.SIGTERM,
            signal.SIGQUIT,
            signal.SIGABRT,
            signal.SIGHUP,
        ):
            signal.signal(sig, _handler)

        for sig in (signal.SIGPIPE, signal.SIGTSTP, signal.SIGTTIN, signal.SIGTTOU):
            signal.signal(sig, signal.SIG_IGN)

    # ------------------------------------------------------------------
    # asyncio event loop

    def _start_event_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        # Make the loop visible to asyncio.get_event_loop() in plugin init().
        asyncio.set_event_loop(self._loop)
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever,
            name="sysrepo-asyncio",
            daemon=True,
        )
        self._loop_thread.start()
        LOG.debug("asyncio event loop started")

    def _stop_event_loop(self) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread:
            self._loop_thread.join(timeout=5.0)
        LOG.debug("asyncio event loop stopped")

    # ------------------------------------------------------------------
    # Plugin lifecycle

    def _discover_plugins(self) -> PluginList:
        discovered: PluginList = []
        for ep in entry_points(group="sysrepo_python.plugins"):
            try:
                cls = ep.load()
                if not (isinstance(cls, type) and issubclass(cls, SysrepoPlugin)):
                    raise TypeError(
                        f"{ep.value!r} must be a SysrepoPlugin subclass, got {cls!r}"
                    )
                discovered.append((ep.name, cls()))
                LOG.debug("discovered plugin %r (%s)", ep.name, ep.value)
            except Exception:
                LOG.exception("failed to load entry point %r", ep.name)
                if self.fatal_fail:
                    raise
        return discovered

    def _init_plugins(self, sess: sysrepo.SysrepoSession) -> None:
        plugins = self._discover_plugins()
        plugins = sort_plugins(sess, plugins)

        for ep_name, inst in plugins:
            try:
                inst.init(sess)
                self._plugins.append((ep_name, inst))
                LOG.info("initialized plugin %r", ep_name)
            except Exception:
                LOG.exception("plugin %r init() failed", ep_name)
                if self.fatal_fail:
                    raise

    def _cleanup_plugins(self, sess: sysrepo.SysrepoSession) -> None:
        for ep_name, inst in reversed(self._plugins):
            try:
                inst.cleanup(sess)
                LOG.info("cleaned up plugin %r", ep_name)
            except Exception:
                LOG.exception("plugin %r cleanup() raised", ep_name)

    # ------------------------------------------------------------------
    # Operational datastore

    def _publish_loaded(self, sess: sysrepo.SysrepoSession) -> None:
        """
        Publish the list of successfully initialised plugins to the
        operational datastore under the augmented sysrepo-python-plugind
        container, leaving the C daemon's loaded-plugins node untouched.
        """
        sess.switch_datastore("operational")
        try:
            sess.discard_items(_LOADED_CONTAINER)
        except sysrepo.SysrepoNotFoundError:
            pass

        for ep_name, _ in self._plugins:
            sess.set_item(_LOADED_XPATH, ep_name)

        sess.apply_changes()
        sess.switch_datastore("running")
        LOG.debug(
            "published %d plugin name(s) to operational datastore",
            len(self._plugins),
        )


# ------------------------------------------------------------------------------
def _sd_notify(state: str) -> None:
    """Send a state notification to systemd if NOTIFY_SOCKET is set."""
    sock_path = os.environ.get("NOTIFY_SOCKET", "")
    if not sock_path:
        return
    # systemd may use an abstract socket (leading '@' means NUL byte).
    addr = "\0" + sock_path[1:] if sock_path.startswith("@") else sock_path
    with contextlib.suppress(OSError):
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(addr)
            s.sendall(state.encode())
