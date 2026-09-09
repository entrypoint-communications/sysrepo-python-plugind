# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import MagicMock, call, patch

import pytest
import sysrepo

from sysrepo_python_plugind.daemon import (
    PluginDaemon,
    _LOADED_CONTAINER,
    _LOADED_XPATH,
)
from sysrepo_python_plugind.loaded_plugin import LoadedPlugin
from sysrepo_python_plugind.plugin import SysrepoPlugin


def _loaded(name, instance=None, session=None):
    """Build a LoadedPlugin with MagicMock defaults for the test suite."""
    return LoadedPlugin(
        name,
        instance if instance is not None else MagicMock(),
        session if session is not None else MagicMock(),
    )


# ---------------------------------------------------------------------------
# Concrete plugin fixtures


class _GoodPlugin(SysrepoPlugin):
    def init(self, session):
        pass


class _FailPlugin(SysrepoPlugin):
    def init(self, session):
        raise RuntimeError("init failed")


class _FailCleanupPlugin(SysrepoPlugin):
    def init(self, session):
        pass

    def cleanup(self, session):
        raise RuntimeError("cleanup failed")


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
    def _patched_init(self, daemon, eps, conn=None):
        conn = conn if conn is not None else MagicMock()
        with patch("sysrepo_python_plugind.daemon.entry_points", return_value=eps):
            with patch(
                "sysrepo_python_plugind.daemon.sort_plugins",
                side_effect=lambda s, p: p,
            ):
                daemon._init_plugins(conn, MagicMock())

    def test_successful_init_appends_to_plugins(self):
        daemon = PluginDaemon()
        self._patched_init(daemon, [_make_ep("p1", _GoodPlugin)])
        assert len(daemon._plugins) == 1
        assert daemon._plugins[0].name == "p1"

    def test_each_plugin_gets_its_own_session(self):
        daemon = PluginDaemon()
        conn = MagicMock()
        sessions = [MagicMock(name="s1"), MagicMock(name="s2")]
        conn.start_session.side_effect = sessions
        self._patched_init(
            daemon,
            [_make_ep("p1", _GoodPlugin), _make_ep("p2", _GoodPlugin)],
            conn=conn,
        )
        assert [lp.session for lp in daemon._plugins] == sessions
        assert conn.start_session.call_count == 2

    def test_failed_init_skipped_non_fatal(self):
        daemon = PluginDaemon(fatal_fail=False)
        self._patched_init(daemon, [_make_ep("bad", _FailPlugin)])
        assert daemon._plugins == []

    def test_failed_init_stops_its_session_non_fatal(self):
        daemon = PluginDaemon(fatal_fail=False)
        conn = MagicMock()
        sess = MagicMock()
        conn.start_session.return_value = sess
        self._patched_init(daemon, [_make_ep("bad", _FailPlugin)], conn=conn)
        sess.stop.assert_called_once()

    def test_failed_init_raises_fatal(self):
        daemon = PluginDaemon(fatal_fail=True)
        with patch("sysrepo_python_plugind.daemon.entry_points",
                   return_value=[_make_ep("bad", _FailPlugin)]):
            with patch("sysrepo_python_plugind.daemon.sort_plugins",
                       side_effect=lambda s, p: p):
                with pytest.raises(RuntimeError, match="init failed"):
                    daemon._init_plugins(MagicMock(), MagicMock())

    def test_good_plugin_after_bad_is_still_initialised(self):
        daemon = PluginDaemon(fatal_fail=False)
        eps = [_make_ep("bad", _FailPlugin), _make_ep("good", _GoodPlugin)]
        self._patched_init(daemon, eps)
        assert daemon._plugins[0].name == "good"


# ---------------------------------------------------------------------------
# _cleanup_plugins


class TestCleanupPlugins:
    def test_cleanup_called_in_reverse_init_order(self):
        log = []
        daemon = PluginDaemon()
        daemon._plugins = [
            _loaded("a", _TrackingPlugin(log, "a")),
            _loaded("b", _TrackingPlugin(log, "b")),
            _loaded("c", _TrackingPlugin(log, "c")),
        ]
        daemon._cleanup_plugins()
        assert [name for _, name in log] == ["c", "b", "a"]

    def test_cleanup_exception_does_not_stop_remaining(self):
        log = []
        daemon = PluginDaemon()
        daemon._plugins = [
            _loaded("a", _TrackingPlugin(log, "a")),
            _loaded("bad", _FailCleanupPlugin()),
            _loaded("c", _TrackingPlugin(log, "c")),
        ]
        daemon._cleanup_plugins()
        # "c" and "a" must both be cleaned up despite "bad" raising
        assert [name for _, name in log] == ["c", "a"]

    def test_cleanup_receives_the_plugins_own_session(self):
        daemon = PluginDaemon()
        inst = MagicMock()
        sess = MagicMock()
        daemon._plugins = [_loaded("a", inst, sess)]
        daemon._cleanup_plugins()
        inst.cleanup.assert_called_once_with(sess)

    def test_each_session_is_stopped_after_cleanup(self):
        daemon = PluginDaemon()
        s1, s2 = MagicMock(), MagicMock()
        daemon._plugins = [_loaded("a", session=s1), _loaded("b", session=s2)]
        daemon._cleanup_plugins()
        s1.stop.assert_called_once()
        s2.stop.assert_called_once()
        assert daemon._plugins == []

    def test_session_stopped_even_when_cleanup_raises(self):
        daemon = PluginDaemon()
        sess = MagicMock()
        daemon._plugins = [_loaded("bad", _FailCleanupPlugin(), sess)]
        daemon._cleanup_plugins()
        sess.stop.assert_called_once()

    def test_stop_plugin_sessions_safety_net(self):
        daemon = PluginDaemon()
        s1, s2 = MagicMock(), MagicMock()
        daemon._plugins = [_loaded("a", session=s1), _loaded("b", session=s2)]
        daemon._stop_plugin_sessions()
        s1.stop.assert_called_once()
        s2.stop.assert_called_once()
        assert daemon._plugins == []


# ---------------------------------------------------------------------------
# _publish_loaded


class TestPublishLoaded:
    def test_writes_plugin_names_to_operational_datastore(self):
        daemon = PluginDaemon()
        daemon._plugins = [_loaded("plugin-a"), _loaded("plugin-b")]
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
