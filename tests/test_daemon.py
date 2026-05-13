# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import MagicMock, call, patch

import pytest
import sysrepo

from sysrepo_python_plugind.daemon import PluginDaemon, _LOADED_CONTAINER, _LOADED_XPATH
from sysrepo_python_plugind.plugin import SysrepoPlugin


# ---------------------------------------------------------------------------
# Concrete plugin fixtures


class _GoodPlugin(SysrepoPlugin):
    def init(self, session):
        pass


class _FailPlugin(SysrepoPlugin):
    def init(self, session):
        raise RuntimeError("init failed")


class _TrackingPlugin(SysrepoPlugin):
    """Records the order in which init/cleanup are called."""

    def __init__(self, log: list, name: str):
        self.log = log
        self.name = name

    def init(self, session):
        self.log.append(("init", self.name))

    def cleanup(self, session):
        self.log.append(("cleanup", self.name))


def _make_ep(name, cls):
    ep = MagicMock()
    ep.name = name
    ep.value = f"tests:{cls.__name__}"
    ep.load.return_value = cls
    return ep


# ---------------------------------------------------------------------------
# _discover_plugins


class TestDiscoverPlugins:
    def test_valid_plugin_is_discovered(self):
        daemon = PluginDaemon()
        with patch(
            "sysrepo_python_plugind.daemon.entry_points",
            return_value=[_make_ep("my-plugin", _GoodPlugin)],
        ):
            plugins = daemon._discover_plugins()

        assert len(plugins) == 1
        assert plugins[0][0] == "my-plugin"
        assert isinstance(plugins[0][1], _GoodPlugin)

    def test_non_subclass_entry_point_is_skipped(self):
        daemon = PluginDaemon()
        ep = MagicMock()
        ep.name = "bad"
        ep.load.return_value = object  # not a SysrepoPlugin subclass
        with patch("sysrepo_python_plugind.daemon.entry_points", return_value=[ep]):
            plugins = daemon._discover_plugins()

        assert plugins == []

    def test_load_error_skipped_non_fatal(self):
        daemon = PluginDaemon(fatal_fail=False)
        ep = MagicMock()
        ep.name = "bad"
        ep.load.side_effect = ImportError("missing dep")
        with patch("sysrepo_python_plugind.daemon.entry_points", return_value=[ep]):
            plugins = daemon._discover_plugins()

        assert plugins == []

    def test_load_error_raises_fatal(self):
        daemon = PluginDaemon(fatal_fail=True)
        ep = MagicMock()
        ep.name = "bad"
        ep.load.side_effect = ImportError("missing dep")
        with patch("sysrepo_python_plugind.daemon.entry_points", return_value=[ep]):
            with pytest.raises(ImportError):
                daemon._discover_plugins()

    def test_multiple_plugins_all_discovered(self):
        daemon = PluginDaemon()
        eps = [_make_ep("p1", _GoodPlugin), _make_ep("p2", _GoodPlugin)]
        with patch("sysrepo_python_plugind.daemon.entry_points", return_value=eps):
            plugins = daemon._discover_plugins()

        assert [n for n, _ in plugins] == ["p1", "p2"]


# ---------------------------------------------------------------------------
# _init_plugins


class TestInitPlugins:
    def _patched_init(self, daemon, eps):
        with patch("sysrepo_python_plugind.daemon.entry_points", return_value=eps):
            with patch(
                "sysrepo_python_plugind.daemon.sort_plugins",
                side_effect=lambda s, p: p,
            ):
                daemon._init_plugins(MagicMock())

    def test_successful_init_appends_to_plugins(self):
        daemon = PluginDaemon()
        self._patched_init(daemon, [_make_ep("p1", _GoodPlugin)])
        assert len(daemon._plugins) == 1
        assert daemon._plugins[0][0] == "p1"

    def test_failed_init_skipped_non_fatal(self):
        daemon = PluginDaemon(fatal_fail=False)
        self._patched_init(daemon, [_make_ep("bad", _FailPlugin)])
        assert daemon._plugins == []

    def test_failed_init_raises_fatal(self):
        daemon = PluginDaemon(fatal_fail=True)
        with patch("sysrepo_python_plugind.daemon.entry_points",
                   return_value=[_make_ep("bad", _FailPlugin)]):
            with patch("sysrepo_python_plugind.daemon.sort_plugins",
                       side_effect=lambda s, p: p):
                with pytest.raises(RuntimeError, match="init failed"):
                    daemon._init_plugins(MagicMock())

    def test_good_plugin_after_bad_is_still_initialised(self):
        daemon = PluginDaemon(fatal_fail=False)
        eps = [_make_ep("bad", _FailPlugin), _make_ep("good", _GoodPlugin)]
        self._patched_init(daemon, eps)
        assert daemon._plugins[0][0] == "good"


# ---------------------------------------------------------------------------
# _cleanup_plugins


class TestCleanupPlugins:
    def test_cleanup_called_in_reverse_init_order(self):
        log = []
        daemon = PluginDaemon()
        daemon._plugins = [
            ("a", _TrackingPlugin(log, "a")),
            ("b", _TrackingPlugin(log, "b")),
            ("c", _TrackingPlugin(log, "c")),
        ]
        daemon._cleanup_plugins(MagicMock())
        assert [name for _, name in log] == ["c", "b", "a"]

    def test_cleanup_exception_does_not_stop_remaining(self):
        log = []
        daemon = PluginDaemon()
        daemon._plugins = [
            ("a", _TrackingPlugin(log, "a")),
            ("bad", _FailPlugin()),
            ("c", _TrackingPlugin(log, "c")),
        ]
        daemon._cleanup_plugins(MagicMock())
        # "c" and "a" must both be cleaned up despite "bad" raising
        assert [name for _, name in log] == ["c", "a"]


# ---------------------------------------------------------------------------
# _publish_loaded


class TestPublishLoaded:
    def test_writes_plugin_names_to_operational_datastore(self):
        daemon = PluginDaemon()
        daemon._plugins = [("plugin-a", MagicMock()), ("plugin-b", MagicMock())]
        sess = MagicMock()

        daemon._publish_loaded(sess)

        sess.switch_datastore.assert_any_call("operational")
        sess.discard_items.assert_called_once_with(_LOADED_CONTAINER)
        sess.set_item.assert_any_call(_LOADED_XPATH, "plugin-a")
        sess.set_item.assert_any_call(_LOADED_XPATH, "plugin-b")
        sess.apply_changes.assert_called_once()
        sess.switch_datastore.assert_called_with("running")

    def test_discard_not_found_is_tolerated(self):
        daemon = PluginDaemon()
        daemon._plugins = []
        sess = MagicMock()
        sess.discard_items.side_effect = sysrepo.SysrepoNotFoundError()

        daemon._publish_loaded(sess)  # must not raise

        sess.apply_changes.assert_called_once()

    def test_no_plugins_writes_nothing(self):
        daemon = PluginDaemon()
        daemon._plugins = []
        sess = MagicMock()

        daemon._publish_loaded(sess)

        sess.set_item.assert_not_called()
