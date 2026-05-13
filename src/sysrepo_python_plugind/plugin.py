# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

from abc import ABC, abstractmethod

import sysrepo


class SysrepoPlugin(ABC):
    """
    Base class for sysrepo Python plugins loaded by sysrepo-python-plugind.

    Install a plugin by declaring an entry point in your package:

        [project.entry-points."sysrepo_python.plugins"]
        my-plugin = "my_package.plugin:MyPlugin"

    The daemon instantiates the class (no constructor arguments), calls
    init() at startup, and cleanup() at shutdown.  State that would be
    stored in sysrepo-plugind's void *private_data is stored as normal
    instance attributes here.
    """

    @abstractmethod
    def init(self, session: sysrepo.SysrepoSession) -> None:
        """
        Called once at daemon startup, after plugin ordering.

        Register subscriptions, allocate resources, and store any
        persistent state as instance attributes.  The session operates
        on SR_DS_RUNNING.

        Raising an exception rejects this plugin.  If the daemon was
        started with --fatal-plugin-fail the whole daemon exits;
        otherwise the next plugin is attempted.
        """

    def cleanup(self, session: sysrepo.SysrepoSession) -> None:
        """
        Called once at daemon shutdown, in reverse init order.

        Subscriptions registered on the session are automatically
        cleaned up when the session stops, so this only needs to
        release external resources (file handles, network connections,
        etc.).  The default implementation does nothing.
        """
