# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

"""Example sysrepo-python-plugind plugin for the example-system YANG module.

This plugin demonstrates two core patterns:

1. **Config change subscription** – reacts when an operator writes a new
   hostname under /example-system:system/hostname.

2. **Operational data provider** – fulfils on-demand GET requests for
   /example-system:system/state by reading real kernel data.

Installation
------------
Install the example-system.yang module into sysrepo first::

    sysrepoctl --install example-system.yang

Then install this package so the entry point is visible to the daemon::

    pip install -e .          # from the examples/ directory

Finally run the daemon::

    sysrepo-python-plugind
"""

from __future__ import annotations

import logging
import platform
from typing import Any, Dict, List, Optional

import sysrepo
from sysrepo.change import Change, ChangeCreated, ChangeDeleted, ChangeModified

from sysrepo_python_plugind import SysrepoPlugin

LOG = logging.getLogger(__name__)

_MODULE = "example-system"
_HOSTNAME_XPATH = f"/{_MODULE}:system/hostname"
_STATE_XPATH = f"/{_MODULE}:system/state"


class ExampleSystemPlugin(SysrepoPlugin):
    """Plugin that manages the example-system YANG module."""

    def init(self, session: sysrepo.SysrepoSession) -> None:
        session.subscribe_module_change(
            _MODULE,
            None,  # subscribe to the whole module
            self._on_config_change,
        )
        session.subscribe_oper_data_request(
            _MODULE,
            _STATE_XPATH,
            self._on_oper_request,
        )
        LOG.info("example-system plugin initialised")

    # ------------------------------------------------------------------
    # Callbacks

    def _on_config_change(
        self,
        event: str,
        req_id: int,
        changes: List[Change],
        private_data: Any,
    ) -> None:
        # sysrepo fires "change" then "done"; act only after the transaction
        # commits so we see the final values.
        LOG.info("_on_config_change called")
        if event != "done":
            return

        for change in changes:
            if change.xpath != _HOSTNAME_XPATH:
                continue
            if isinstance(change, (ChangeCreated, ChangeModified)):
                LOG.info("hostname set to %r", change.value)
                # A real plugin would call socket.sethostname(change.value) here,
                # guarded by a try/except for permission errors.
            elif isinstance(change, ChangeDeleted):
                LOG.info("hostname deleted")

    def _on_oper_request(
        self,
        xpath: str,
        private_data: Any,
    ) -> Optional[Dict]:
        LOG.info("_on_oper_request called")
        # Return data in libyang dict format: top-level key is "module:node".
        return {
            f"{_MODULE}:system": {
                "state": {
                    "uptime-seconds": _read_uptime(),
                    "kernel-version": platform.release(),
                }
            }
        }


# ------------------------------------------------------------------------------

def _read_uptime() -> int:
    """Return system uptime in whole seconds by reading /proc/uptime."""
    with open("/proc/uptime") as fh:
        return int(float(fh.read().split()[0]))
