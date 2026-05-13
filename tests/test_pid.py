# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

import os

import pytest

from sysrepo_python_plugind.pid import PidFile


class TestPidFile:
    def test_creates_file_on_enter(self, tmp_path):
        path = str(tmp_path / "test.pid")
        with PidFile(path):
            assert os.path.exists(path)

    def test_file_has_correct_permissions(self, tmp_path):
        path = str(tmp_path / "test.pid")
        with PidFile(path):
            assert (os.stat(path).st_mode & 0o777) == 0o640

    def test_write_stores_current_pid(self, tmp_path):
        path = str(tmp_path / "test.pid")
        with PidFile(path) as pf:
            pf.write()
            content = open(path).read().strip()
        assert content == str(os.getpid())

    def test_exit_unlinks_file(self, tmp_path):
        path = str(tmp_path / "test.pid")
        with PidFile(path):
            pass
        assert not os.path.exists(path)

    def test_exit_fd_is_cleared(self, tmp_path):
        path = str(tmp_path / "test.pid")
        with PidFile(path) as pf:
            pass
        assert pf._fd is None

    def test_second_instance_raises(self, tmp_path):
        # POSIX lockf is per-process: two fds in the same process don't conflict,
        # so we must use a child process to exercise the lock.
        import multiprocessing as mp

        path = str(tmp_path / "test.pid")

        def _try_lock(q):
            try:
                with PidFile(path):
                    q.put("no_error")
            except RuntimeError:
                q.put("runtime_error")

        with PidFile(path):
            q = mp.Queue()
            proc = mp.Process(target=_try_lock, args=(q,))
            proc.start()
            proc.join(timeout=5)
            assert q.get_nowait() == "runtime_error"

    def test_exit_tolerates_already_unlinked_file(self, tmp_path):
        path = str(tmp_path / "test.pid")
        with PidFile(path) as pf:
            os.unlink(path)
        # __exit__ should not raise FileNotFoundError

    def test_write_is_noop_when_fd_is_none(self):
        pf = PidFile("/nonexistent/path")
        pf._fd = None
        pf.write()  # must not raise

    def test_write_overwrites_previous_content(self, tmp_path):
        path = str(tmp_path / "test.pid")
        with PidFile(path) as pf:
            pf.write()
            pf.write()  # second write should not append
            content = open(path).read()
        assert content.count("\n") == 1
