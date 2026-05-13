# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC, abstractmethod

import sysrepo


class SysrepoPlugin(ABC):
    """Abstract base class for sysrepo Python plugins.

    Plugins are discovered by sysrepo-python-plugind via the
    ``sysrepo_python.plugins`` entry point group.  Declare a plugin in
    your package's ``pyproject.toml``::

        [project.entry-points."sysrepo_python.plugins"]
        my-plugin = "my_package.plugin:MyPlugin"

    The daemon instantiates the class with no arguments, calls
    :meth:`init` at startup (after plugin ordering), and :meth:`cleanup`
    at shutdown in reverse init order.  State that the C daemon stored in
    ``void *private_data`` should be stored as instance attributes.
    """

    @abstractmethod
    def init(self, session: sysrepo.session.SysrepoSession) -> None:
        """Initialise the plugin at daemon startup.

        Called once after plugin ordering and before ``sd_notify("READY=1")``.
        Register sysrepo subscriptions and allocate resources here.  The
        session is on ``SR_DS_RUNNING`` and is shared with all other plugins.

        Args:
            session (sysrepo.session.SysrepoSession): Active running-datastore
                session shared across all plugins.

        Raises:
            Exception: Signals rejection of this plugin.  With
                ``--fatal-plugin-fail`` the daemon exits; otherwise this
                plugin is skipped and the next one is attempted.
        """

    def cleanup(self, session: sysrepo.session.SysrepoSession) -> None:
        """Clean up plugin resources at daemon shutdown.

        Called once in reverse init order after a stop signal is received.
        Sysrepo subscriptions created on the session are automatically
        released when the session closes, so this method only needs to
        release external resources (file handles, network connections, etc.).

        The default implementation does nothing.

        Args:
            session (sysrepo.session.SysrepoSession): Active running-datastore
                session shared across all plugins.
        """
