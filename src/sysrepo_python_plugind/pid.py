# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

import fcntl
import logging
import os

LOG = logging.getLogger(__name__)


class PidFile:
    """
    POSIX PID file with exclusive lock.

    Matches the C daemon's behaviour:
    * Open and lock BEFORE daemonizing so that a second invocation fails
      immediately, even before the first instance has written its PID.
    * write() is called AFTER plugins have initialised so that the file
      contains the daemonized child's PID, not the parent's.
    * On exit the file is closed and unlinked.

    Use as a context manager::

        with PidFile("/run/sysrepo-python-plugind.pid") as pid_file:
            _daemonize()
            # ... init plugins ...
            pid_file.write()
    """

    __slots__ = ("path", "_fd")

    def __init__(self, path: str) -> None:
        self.path = path
        self._fd: int | None = None

    def __enter__(self) -> "PidFile":
        self._fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o640)
        try:
            fcntl.lockf(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self._fd)
            self._fd = None
            raise RuntimeError(
                f"another sysrepo-python-plugind instance is running "
                f"(cannot lock {self.path})"
            ) from exc
        return self

    def write(self) -> None:
        """Write the current process PID. Call after daemonizing."""
        if self._fd is None:
            return
        pid_bytes = f"{os.getpid()}\n".encode()
        os.ftruncate(self._fd, 0)
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.write(self._fd, pid_bytes)
        LOG.debug("wrote PID %d to %s", os.getpid(), self.path)

    def __exit__(self, *_) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
