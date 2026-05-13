# Stub out the sysrepo C extension before any project module imports it,
# so the test suite runs without libsysrepo.so installed.

import sys
from types import ModuleType
from unittest.mock import MagicMock


class _SysrepoNotFoundError(Exception):
    pass


_stub = ModuleType("sysrepo")
_stub.SysrepoSession = MagicMock          # used only as a type annotation target
_stub.SysrepoConnection = MagicMock       # context manager in daemon.run()
_stub.SysrepoNotFoundError = _SysrepoNotFoundError
_stub.configure_logging = MagicMock()

sys.modules["sysrepo"] = _stub
