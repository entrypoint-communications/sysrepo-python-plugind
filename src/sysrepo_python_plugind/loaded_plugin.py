# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

from dataclasses import dataclass

import sysrepo

from .plugin import SysrepoPlugin


@dataclass
class LoadedPlugin:
    """A successfully initialised plugin and the session bound to it.

    Each plugin owns a dedicated ``SysrepoSession`` for the whole of its
    lifetime.  The same session object is passed to :meth:`SysrepoPlugin.init`
    and later to :meth:`SysrepoPlugin.cleanup`, and is stopped by the daemon
    only after ``cleanup()`` returns — so a plugin can unsubscribe and touch
    the datastore during shutdown using the very session its subscriptions
    were created on.

    Attributes:
        name (str): Entry-point name identifying the plugin.
        instance (SysrepoPlugin): The plugin instance.
        session (sysrepo.session.SysrepoSession): The plugin's private
            running-datastore session.
    """

    name: str
    instance: SysrepoPlugin
    session: "sysrepo.session.SysrepoSession"
