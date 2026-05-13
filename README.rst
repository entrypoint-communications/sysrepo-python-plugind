sysrepo-python-plugind
======================

A Python reimplementation of ``sysrepo-plugind`` — the sysrepo plugin daemon.

The C daemon loads compiled ``.so`` plugins via ``dlopen``.  This daemon loads
**Python plugins** discovered via entry points (``importlib.metadata``), giving
plugin authors a pure-Python development experience against the existing
`sysrepo-python`_ CFFI bindings.

The two daemons can run **simultaneously**: the Python daemon manages its own
YANG subtree (``python-plugin-order``, ``python-loaded-plugins``) and never
touches the C daemon's nodes.

.. _sysrepo-python: https://github.com/sysrepo/sysrepo-python


Requirements
------------

- Python ≥ 3.10
- sysrepo-python_ (and the underlying ``libsysrepo.so``)
- sysrepo core ≥ 2022-08-26 (ships ``sysrepo-plugind@2022-08-26.yang``)


Installation
------------

.. code-block:: console

   pip install sysrepo-python-plugind

Then register the YANG augmentation module with sysrepo (requires write
access to the sysrepo repository, typically run as root):

.. code-block:: console

   sysrepo-python-plugind-setup

This is idempotent — safe to run on every deployment or system boot.  Pass
``--force`` to upgrade the module after a package update.


Writing a plugin
----------------

Subclass ``SysrepoPlugin`` and implement ``init()``.  Register the class via
an entry point in your package's ``pyproject.toml``:

.. code-block:: toml

   [project.entry-points."sysrepo_python.plugins"]
   my-plugin = "my_package.plugin:MyPlugin"

Installing your package makes the plugin visible to the daemon immediately —
no copying of files or environment variables required.

Minimal example:

.. code-block:: python

   import logging
   import sysrepo
   from sysrepo_python_plugind import SysrepoPlugin

   LOG = logging.getLogger(__name__)

   class MyPlugin(SysrepoPlugin):

       def init(self, session: sysrepo.SysrepoSession) -> None:
           self._counter = 0
           session.subscribe_module_change(
               "my-module", None, self._on_change, done_only=True
           )
           session.subscribe_oper_data_request(
               "my-module", "/my-module:stats", self._on_oper
           )
           LOG.info("MyPlugin ready")

       def cleanup(self, session: sysrepo.SysrepoSession) -> None:
           LOG.info("MyPlugin stopping (counter=%d)", self._counter)

       def _on_change(self, event, req_id, changes, priv):
           self._counter += 1

       def _on_oper(self, xpath, priv):
           return {"my-module": {"stats": {"change-count": self._counter}}}

State that the C daemon stored in ``void *private_data`` is stored as instance
attributes (``self._counter`` above).

Async callbacks
~~~~~~~~~~~~~~~

The daemon starts an asyncio event loop in a background thread before calling
any ``init()``, so plugins can use ``asyncio_register=True`` subscriptions
without managing a loop themselves:

.. code-block:: python

   class AsyncMyPlugin(SysrepoPlugin):

       def init(self, session: sysrepo.SysrepoSession) -> None:
           session.subscribe_module_change(
               "my-module", None, self._on_change,
               done_only=True, asyncio_register=True,
           )

       async def _on_change(self, event, req_id, changes, priv):
           ...


Running the daemon
------------------

.. code-block:: console

   # Foreground, INFO-level logging to stderr:
   sysrepo-python-plugind -d -v 2

   # Background (daemonize), write PID file:
   sysrepo-python-plugind -p /run/sysrepo-python-plugind.pid

CLI flags mirror those of the C ``sysrepo-plugind``:

==========  ===============================================================
``-d``      Stay in foreground; log to stderr instead of syslog
``-v LEVEL``  Verbosity: 0=ERROR 1=WARNING 2=INFO 3=DEBUG (default: 2)
``-p PATH``   Write PID file at PATH
``-f``      Exit if any plugin fails to initialise (default: skip and continue)
==========  ===============================================================


Plugin ordering
---------------

By default plugins are initialised in entry-point discovery order.  To
override this, set the ``python-plugin-order`` leaf-list in sysrepo's running
datastore:

.. code-block:: console

   sysrepocfg -d running --edit

Add under ``/sysrepo-plugind:sysrepo-plugind``:

.. code-block:: xml

   <python-plugin-order xmlns="urn:sysrepo:python-plugind">
     <plugin>my-plugin</plugin>
     <plugin>other-plugin</plugin>
   </python-plugin-order>

Plugins absent from the list are appended after the ordered set, preserving
their discovery order.  A trailing file extension in a configured name (e.g.
``my-plugin.so``) is stripped before comparison, so operator configs written
for the C daemon can be reused unchanged.

The list of successfully initialised plugins is published to the operational
datastore at ``/sysrepo-plugind:sysrepo-plugind/sysrepo-python-plugind:python-loaded-plugins/plugin``.


Systemd deployment
------------------

A service file is provided in the ``systemd/`` directory of the source
distribution:

.. code-block:: console

   cp systemd/sysrepo-python-plugind.service /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now sysrepo-python-plugind

The service runs ``sysrepo-python-plugind-setup`` as ``ExecStartPre=``,
ensuring the YANG module is present before the daemon starts.

If the daemon binary is not at ``/usr/bin/sysrepo-python-plugind`` (e.g. when
installed into a virtual environment), update the ``ExecStartPre=`` and
``ExecStart=`` paths in the service file accordingly.


License
-------

BSD-3-Clause — same as sysrepo-python.
