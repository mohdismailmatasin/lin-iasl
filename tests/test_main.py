"""Tests for Lin-IASL"""

import unittest
from gi.repository import Gtk
import pytest

# ensure GTK has a display; if not, skip the whole module
if not Gtk.init_check([]):
    pytest.skip("GTK not available (no display)", allow_module_level=True)

# also import the new helper modules so we can test them directly
from lin_iasl import search, tabs


class TestLinIasl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # window creation touches UI so do it once in a known-good environment
        if not Gtk.init_check([]):
            raise unittest.SkipTest("GTK initialization failed")

    def test_placeholder(self):
        self.assertTrue(True)

    def test_dark_theme_flag(self):
        # window should expose dark_theme and default to True
        from lin_iasl.main import LinIaslWindow
        win = LinIaslWindow()
        self.assertTrue(hasattr(win, 'dark_theme'))
        self.assertTrue(win.dark_theme)

    def test_search_and_replace_helpers(self):
        """Low-level buffer search/replace operations should behave as
        expected regardless of the UI.
        """
        from lin_iasl.main import LinIaslWindow
        win = LinIaslWindow()
        buf = Gtk.TextBuffer()
        buf.set_text("foo bar foo baz foo")

        start = buf.get_start_iter()
        # simple find next using window helper (wrapper)
        match = win._search_buffer(buf, "foo", start)
        self.assertIsNotNone(match)
        s, e = match
        self.assertEqual(buf.get_text(s, e, False), "foo")

        # also call the underlying search module directly
        match2 = search.search_buffer(buf, "foo", start)
        self.assertEqual(match, match2)

        # case-insensitive
        buf.set_text("Foo")
        match = win._search_buffer(buf, "foo", buf.get_start_iter(), case_sensitive=False)
        self.assertIsNotNone(match)

        # highlight helper should exist
        buf.set_text("x x")
        search.highlight_all_matches(buf, "x")
        tag = buf.get_tag_table().lookup("search-highlight")
        self.assertIsNotNone(tag)
        search.clear_highlights(buf)

        # replace-all logic roughly testable via window helper
        buf.set_text("aaa")
        count = 0
        iter_ = buf.get_start_iter()
        while True:
            m = win._search_buffer(buf, "a", iter_)
            if not m:
                break
            s,e = m
            buf.delete(s,e)
            buf.insert(s, "b")
            count += 1
            iter_ = buf.get_iter_at_offset(s.get_offset()+1)
        self.assertEqual(count, 3)
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), "bbb")

        # highlights should be removable and no-op for empty search
        buf.set_text("x y x")
        win._highlight_all_matches(buf, "x")
        # there should be a tag now
        tag = buf.get_tag_table().lookup("search-highlight")
        self.assertIsNotNone(tag)
        win._clear_highlights(buf)
        # ensure tag removed from entire buffer
        start, end = buf.get_start_iter(), buf.get_end_iter()
        # iterate to check no tag remains
        it = start.copy()
        found = False
        while it.compare(end) < 0:
            tags = it.get_tags()
            if tag in tags:
                found = True
                break
            it.forward_char()
        self.assertFalse(found)
        # empty search shouldn't crash
        win._highlight_all_matches(buf, "")

    def test_tabs_helpers(self):
        """Verify that tab-related helpers can be invoked without failure."""
        from lin_iasl.main import LinIaslWindow
        win = LinIaslWindow()
        # ensure there is at least one tab
        buf = win._get_current_tab()['buffer']
        buf.set_text("/* comment */ 42")
        # calling syntax highlighter should not raise
        tabs.apply_syntax_highlighting(buf, buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False))
        # updating navigator should also succeed (no exceptions)
        tabs.update_navigator(win)
        # filter / selection callbacks can be invoked in isolation
        entry = Gtk.Entry(); entry.set_text("")
        win._on_filter_changed(entry)
        # nav selection - nothing selected, should be safe
        sel = win.nav_tree.get_selection()
        win._on_nav_selection_changed(sel)


if __name__ == "__main__":
    unittest.main()