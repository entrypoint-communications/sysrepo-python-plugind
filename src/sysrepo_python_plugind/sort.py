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
    """
    Reorder *plugins* according to the operator-configured plugin-order.

    Mirrors srpd_sort_plugins() from sysrepo/src/executables/srpd_common.c:

    * Read the leaf-list at /sysrepo-plugind:sysrepo-plugind/
      sysrepo-python-plugind:python-plugin-order/plugin from the running
      datastore (ordered-by user).
    * For each name in that list, find the matching plugin in *plugins* and
      move it to the front, preserving relative YANG order.
    * Plugins not mentioned in the YANG list keep their original discovery
      order and appear after all ordered plugins.
    * Names in the YANG list that don't match any loaded plugin are silently
      ignored (same behaviour as the C daemon).

    File extensions in the configured name are stripped before comparison so
    that operators familiar with the C daemon can reuse entries like
    "my_plugin.so".
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
    """Strip the last file extension, if any (e.g. 'foo.so' → 'foo')."""
    dot = name.rfind(".")
    return name[:dot] if dot >= 0 else name
