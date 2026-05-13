# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

import logging
from typing import TYPE_CHECKING

import sysrepo

if TYPE_CHECKING:
    from .plugin import SysrepoPlugin

LOG = logging.getLogger(__name__)

_ORDER_XPATH = (
    "/sysrepo-plugind:sysrepo-plugind"
    "/sysrepo-python-plugind:python-plugin-order/plugin"
)

# Type alias for the (entry-point-name, instance) pairs the daemon works with.
PluginList = list[tuple[str, "SysrepoPlugin"]]


def sort_plugins(session: sysrepo.SysrepoSession, plugins: PluginList) -> PluginList:
    """Reorder plugins according to the operator-configured plugin order.

    Reads the ``python-plugin-order`` leaf-list from the sysrepo running
    datastore and performs a stable partition: configured plugins are moved
    to the front in YANG list order; unconfigured plugins retain their
    original discovery order at the end.

    Mirrors ``srpd_sort_plugins()`` from
    ``sysrepo/src/executables/srpd_common.c``.

    Args:
        session (sysrepo.SysrepoSession): Active running-datastore session
            used to read the python-plugin-order configuration.
        plugins (PluginList): Discovered (entry-point-name, instance) pairs
            in discovery order.  The input list is not modified.

    Returns:
        PluginList: Reordered (entry-point-name, instance) pairs.
            Configured plugins appear first in YANG list order; remaining
            plugins follow in their original discovery order.

    Raises:
        sysrepo.SysrepoNotFoundError: Caught internally when no
            plugin-order is configured; treated as an empty list and the
            original order is returned unchanged.
    """
    try:
        # String(Value, str) — each item IS a Python str already.
        configured = [_strip_ext(v) for v in session.get_items(_ORDER_XPATH)]
    except sysrepo.SysrepoNotFoundError:
        LOG.debug("no plugin-order configured, using discovery order")
        return plugins

    if not configured:
        return plugins

    LOG.debug("plugin-order from sysrepo: %s", configured)

    ordered: PluginList = []
    remaining = list(plugins)

    for cfg_name in configured:
        for i, (ep_name, inst) in enumerate(remaining):
            if _strip_ext(ep_name) == cfg_name:
                ordered.append(remaining.pop(i))
                LOG.debug("placed plugin %r at position %d", ep_name, len(ordered))
                break
        # cfg_name not found among loaded plugins — ignore, per C implementation.

    return ordered + remaining


def _strip_ext(name: str) -> str:
    """Strip the last file extension from a plugin name, if any.

    Used to normalise operator-configured names (e.g. ``'my_plugin.so'``)
    to match Python entry-point names (e.g. ``'my_plugin'``), preserving
    compatibility with operator configs written for the C daemon.

    Args:
        name (str): Plugin name, optionally including a file extension.

    Returns:
        str: Name with the last dot-suffix removed, or the original name
            if no dot is present.
    """
    dot = name.rfind(".")
    return name[:dot] if dot >= 0 else name
