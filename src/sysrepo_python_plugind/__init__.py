# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

"""sysrepo-python-plugind — Python plugin daemon for sysrepo.

Public API:

- :class:`SysrepoPlugin`: Abstract base class for Python plugins.
- :func:`main`: Entry point for the ``sysrepo-python-plugind`` console script.
"""

from .cli import main
from .plugin import SysrepoPlugin

__all__ = ["SysrepoPlugin", "main"]
