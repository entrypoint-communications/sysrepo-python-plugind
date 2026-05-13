# Copyright (c) 2026 EntryPoint Communications, LLC
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import MagicMock

import pytest
import sysrepo

from sysrepo_python_plugind.sort import _strip_ext, sort_plugins


# ---------------------------------------------------------------------------
# _strip_ext


class TestStripExt:
    def test_no_extension(self):
        assert _strip_ext("my_plugin") == "my_plugin"

    def test_single_extension(self):
        assert _strip_ext("my_plugin.so") == "my_plugin"

    def test_strips_only_last_extension(self):
        assert _strip_ext("my_plugin.so.1") == "my_plugin.so"

    def test_empty_string(self):
        assert _strip_ext("") == ""


# ---------------------------------------------------------------------------
# sort_plugins helpers


def _session(configured=None, not_found=False):
    sess = MagicMock()
    if not_found:
        sess.get_items.side_effect = sysrepo.SysrepoNotFoundError()
    else:
        sess.get_items.return_value = configured or []
    return sess


def _plugins(*names):
    return [(name, MagicMock()) for name in names]


# ---------------------------------------------------------------------------
# sort_plugins


class TestSortPlugins:
    def test_not_found_returns_original_order(self):
        result = sort_plugins(_session(not_found=True), _plugins("a", "b", "c"))
        assert [n for n, _ in result] == ["a", "b", "c"]

    def test_empty_config_returns_original_order(self):
        result = sort_plugins(_session(configured=[]), _plugins("a", "b", "c"))
        assert [n for n, _ in result] == ["a", "b", "c"]

    def test_partial_config_moves_named_to_front(self):
        result = sort_plugins(_session(configured=["c", "a"]), _plugins("a", "b", "c"))
        assert [n for n, _ in result] == ["c", "a", "b"]

    def test_full_config_reorders_all(self):
        result = sort_plugins(_session(configured=["b", "c", "a"]), _plugins("a", "b", "c"))
        assert [n for n, _ in result] == ["b", "c", "a"]

    def test_unknown_config_names_silently_ignored(self):
        result = sort_plugins(_session(configured=["x", "a"]), _plugins("a", "b"))
        assert [n for n, _ in result] == ["a", "b"]

    def test_extension_in_config_matches_bare_name(self):
        # Operator config written for the C daemon uses e.g. "b.so"
        result = sort_plugins(_session(configured=["b.so"]), _plugins("a", "b"))
        assert [n for n, _ in result] == ["b", "a"]

    def test_plugin_instances_are_preserved(self):
        inst_a, inst_b = MagicMock(), MagicMock()
        result = sort_plugins(
            _session(configured=["b"]), [("a", inst_a), ("b", inst_b)]
        )
        assert result == [("b", inst_b), ("a", inst_a)]

    def test_input_list_is_not_mutated(self):
        plugins = _plugins("a", "b", "c")
        original = list(plugins)
        sort_plugins(_session(configured=["c", "a"]), plugins)
        assert plugins == original
