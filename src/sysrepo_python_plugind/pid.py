# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

import fcntl
import logging
import os

LOG = logging.getLogger(__name__)


class PidFile:
    """POSIX PID file with exclusive advisory lock.

    Matches the C sysrepo-plugind behaviour:

    - Open and lock **before** daemonizing so a second invocation fails
      immediately, even before the first instance writes its PID.
    - :meth:`write` is called **after** plugins have initialised so the
      file contains the daemonized child's PID, not the parent's.
    - On exit the file is closed and unlinked.

    Args:
        path (str): Filesystem path for the PID file.

    Example::

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
        """Open and exclusively lock the PID file.

        Returns:
            PidFile: self, for use as a context manager.

        Raises:
            RuntimeError: If the exclusive lock cannot be acquired because
                another instance of the daemon already holds it.
        """
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
        """Write the current process PID to the file.

        Truncates any existing content before writing so the file always
        contains exactly one line.  Should be called after daemonizing so
        the written PID belongs to the final child process, not the
        pre-fork parent.
        """
        if self._fd is None:
            return
        pid_bytes = f"{os.getpid()}\n".encode()
        os.ftruncate(self._fd, 0)
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.write(self._fd, pid_bytes)
        LOG.debug("wrote PID %d to %s", os.getpid(), self.path)

    def __exit__(self, *_) -> None:
        """Close and unlink the PID file.

        Silently ignores FileNotFoundError in case the file was already
        removed externally.

        Args:
            *_: Exception info from the ``with`` block; not used.
        """
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
