import re
from typing import Optional

from gi.repository import Gtk


def search_buffer(
    buffer: Gtk.TextBuffer,
    text: str,
    start_iter: Gtk.TextIter,
    forward: bool = True,
    case_sensitive: bool = False,
    regex: bool = False,
    word_only: bool = False,
) -> Optional[tuple]:
    """Search |buffer| for |text|, returning a (start, end) tuple or None.

    See documentation embedded in main.py for details and rationale around
    portability.  This helper is factored out so that other modules and tests
    can call it directly without needing a window instance.
    """
    # try to use the native search API if available
    if hasattr(buffer, "forward_search") and hasattr(buffer, "backward_search"):
        flags = Gtk.TextSearchFlags(0)
        if not case_sensitive:
            flags |= Gtk.TextSearchFlags.CASE_INSENSITIVE
        if regex:
            flags |= Gtk.TextSearchFlags.REGULAR_EXPRESSION
        if word_only:
            flags |= Gtk.TextSearchFlags.WHOLE_WORD

        if forward:
            return buffer.forward_search(text, flags, start_iter)
        else:
            return buffer.backward_search(text, flags, start_iter)

    # fallback: perform manual search in the buffer text
    end_iter = buffer.get_end_iter()
    text_content = buffer.get_text(start_iter, end_iter, False)
    if not case_sensitive:
        haystack = text_content.lower()
        needle = text.lower()
    else:
        haystack = text_content
        needle = text

    if regex:
        match_obj = re.search(needle, haystack)
        if not match_obj:
            return None
        start_off = match_obj.start()
        end_off = match_obj.end()
    else:
        idx = haystack.find(needle)
        if idx < 0:
            return None
        start_off = idx
        end_off = idx + len(needle)

    s_iter = buffer.get_iter_at_offset(start_iter.get_offset() + start_off)
    e_iter = buffer.get_iter_at_offset(start_iter.get_offset() + end_off)
    return (s_iter, e_iter)


def highlight_all_matches(
    buffer: Gtk.TextBuffer,
    text: str,
    case_sensitive: bool = False,
    regex: bool = False,
    word_only: bool = False,
) -> None:
    """Apply a temporary highlight tag to every occurrence of |text| in |buffer|.

    Existing highlights are cleared first.  This function is public so tests
    can verify its behaviour directly.
    """
    tag = buffer.get_tag_table().lookup("search-highlight")
    if not tag:
        tag = buffer.create_tag("search-highlight", background="yellow")

    start = buffer.get_start_iter()
    end = buffer.get_end_iter()
    buffer.remove_tag(tag, start, end)

    if not text:
        return

    iter_ = start
    while True:
        match = search_buffer(buffer, text, iter_, True, case_sensitive, regex, word_only)
        if not match:
            break
        s, e = match
        buffer.apply_tag(tag, s, e)
        iter_ = e


def clear_highlights(buffer: Gtk.TextBuffer) -> None:
    """Remove any search‑highlight tags from |buffer|."""
    tag = buffer.get_tag_table().lookup("search-highlight")
    if tag:
        buffer.remove_tag(tag, buffer.get_start_iter(), buffer.get_end_iter())


def create_search_dialog(parent: Gtk.Window, replace: bool = False) -> Gtk.Dialog:
    """Return a configured dialog for searching (and optionally replacing).

    The dialog instance is returned with several attributes attached (e.g.
    ``_find_entry``) so that callers can inspect user input after ``run()``.
    This mirrors the logic that previously lived inside LinIaslWindow.
    """
    title = "Find & Replace" if replace else "Find"
    dialog = Gtk.Dialog(title=title, parent=parent, flags=0)
    dialog.add_buttons(Gtk.STOCK_FIND, Gtk.ResponseType.OK,
                       Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    if replace:
        dialog.add_button("Replace", Gtk.ResponseType.APPLY)
        dialog.add_button("Replace All", Gtk.ResponseType.YES)

    grid = Gtk.Grid(column_spacing=6, row_spacing=6, margin=12)
    dialog.get_content_area().add(grid)

    grid.attach(Gtk.Label(label="Find:"), 0, 0, 1, 1)
    find_entry = Gtk.Entry()
    find_entry.set_width_chars(40)
    grid.attach(find_entry, 1, 0, 2, 1)

    if replace:
        grid.attach(Gtk.Label(label="Replace:"), 0, 1, 1, 1)
        replace_entry = Gtk.Entry()
        replace_entry.set_width_chars(40)
        grid.attach(replace_entry, 1, 1, 2, 1)
    else:
        replace_entry = None

    case_cb = Gtk.CheckButton(label="Case sensitive")
    grid.attach(case_cb, 0, 2, 1, 1)
    word_cb = Gtk.CheckButton(label="Whole word")
    grid.attach(word_cb, 1, 2, 1, 1)
    regex_cb = Gtk.CheckButton(label="Regex")
    grid.attach(regex_cb, 2, 2, 1, 1)

    dialog._find_entry = find_entry
    dialog._replace_entry = replace_entry
    dialog._case_cb = case_cb
    dialog._word_cb = word_cb
    dialog._regex_cb = regex_cb

    dialog.show_all()
    return dialog
