import os
import re
from typing import Any

from gi.repository import Gtk, Pango


# -------- tab/navigation helpers --------

def apply_syntax_highlighting(text_buffer, buffer_text: str) -> None:
    """Apply syntax highlighting tags to the given buffer content.

    This is effectively the previous method from LinIaslWindow but pulled out
    so that the window class can remain focused on UI wiring and high-level
    actions.  It operates directly on the buffer that has already been filled
    with text.
    """
    # Multiline comments /* ... */
    for match in re.finditer(r'/\*.*?\*/', buffer_text, re.DOTALL):
        start = text_buffer.get_iter_at_offset(match.start())
        end = text_buffer.get_iter_at_offset(match.end())
        text_buffer.apply_tag_by_name("comment", start, end)

    # Single-line comments //
    for match in re.finditer(r'//.*', buffer_text):
        start = text_buffer.get_iter_at_offset(match.start())
        end = text_buffer.get_iter_at_offset(match.end())
        text_buffer.apply_tag_by_name("comment", start, end)

    # String literals
    for match in re.finditer(r'"[^"]*"', buffer_text):
        start = text_buffer.get_iter_at_offset(match.start())
        end = text_buffer.get_iter_at_offset(match.end())
        text_buffer.apply_tag_by_name("string", start, end)

    # Numeric literals
    for match in re.finditer(r'\b\d+\b', buffer_text):
        start = text_buffer.get_iter_at_offset(match.start())
        end = text_buffer.get_iter_at_offset(match.end())
        text_buffer.apply_tag_by_name("number", start, end)

    # Operators
    for match in re.finditer(r'[+\-*/=<>!&|]', buffer_text):
        start = text_buffer.get_iter_at_offset(match.start())
        end = text_buffer.get_iter_at_offset(match.end())
        text_buffer.apply_tag_by_name("operator", start, end)


def update_navigator(window: "Gtk.Window") -> None:
    """Refresh the navigator tree to reflect the current tab's contents.

    The implementation was previously a large method on the window class; it
    has been moved here so that the window file can concentrate on constructing
    menus and handling high-level events.  The |window| argument is expected to
    expose the same attributes used in the original implementation (nav_store,
    tabs, notebook, etc.).
    """
    window.nav_store.clear()
    tab = window._get_current_tab()
    if not tab:
        return

    text_buffer = tab['buffer']
    buffer_text = text_buffer.get_text(
        text_buffer.get_start_iter(), text_buffer.get_end_iter(), False
    )

    # Remove old syntax highlighting tags
    text_buffer.remove_all_tags(
        text_buffer.get_start_iter(), text_buffer.get_end_iter()
    )

    # Extract ACPI objects (DefinitionBlock, Device, Method, etc.)
    object_pattern = re.compile(
        r'^\s*(DefinitionBlock|Device|Method|Scope|Processor|ThermalZone|PowerResource|Name)\s*\(',
        re.MULTILINE | re.IGNORECASE
    )

    for match in object_pattern.finditer(buffer_text):
        line_start = buffer_text.rfind('\n', 0, match.start()) + 1
        line_end = buffer_text.find('\n', match.start())
        if line_end == -1:
            line_end = len(buffer_text)
        current_line = buffer_text[line_start:line_end].strip()

        # Extract object name from the line
        name_match = re.search(r'\("?([^"\s,]+)"?', current_line)
        object_name = name_match.group(1) if name_match else match.group(1)
        offset = match.start()
        window.nav_store.append(None, [object_name, offset])

        # Apply keyword highlighting
        keyword_start = text_buffer.get_iter_at_offset(match.start())
        keyword_end = text_buffer.get_iter_at_offset(match.end())
        text_buffer.apply_tag_by_name("keyword", keyword_start, keyword_end)

        # Apply object name highlighting
        if name_match:
            name_offset_start = match.start() + name_match.start(1)
            name_offset_end = match.start() + name_match.end(1)
            name_start = text_buffer.get_iter_at_offset(name_offset_start)
            name_end = text_buffer.get_iter_at_offset(name_offset_end)
            text_buffer.apply_tag_by_name("function", name_start, name_end)

    # Apply generic syntax highlighting
    apply_syntax_highlighting(text_buffer, buffer_text)

    # Refilter navigator
    if hasattr(window, 'nav_filter'):
        window.nav_filter.refilter()


def nav_filter_func(model: Gtk.TreeModel, tree_iter: Gtk.TreeIter, data: Any = None) -> bool:
    """Filter function used by the navigator filter model."""
    if not hasattr(model, 'get_iter'):  # sanity check
        return True
    pattern = ''
    # the window instance is stored in the filter's "owner" property if set
    # fallback: try to access nav_filter_entry through the model's parent
    try:
        entry = model.get_property('self').nav_filter_entry
        pattern = entry.get_text().lower()
    except Exception:
        pass
    if not pattern:
        return True
    name = model.get_value(tree_iter, 0)
    return pattern in name.lower()


def on_filter_changed(window: Gtk.Window, entry: Gtk.Entry) -> None:
    """Callback for when the navigator filter text is changed."""
    if hasattr(window, 'nav_filter'):
        window.nav_filter.refilter()


def on_nav_selection_changed(window: Gtk.Window, selection: Gtk.TreeSelection) -> None:
    """Callback when the selection in the navigator changes."""
    model, tree_iter = selection.get_selected()
    if tree_iter:
        offset = model.get_value(tree_iter, 1)
        tab = window._get_current_tab()
        if tab:
            buffer_obj = tab['buffer']
            iter_obj = buffer_obj.get_iter_at_offset(offset)
            buffer_obj.select_range(iter_obj, iter_obj)
            tab['view'].scroll_to_iter(iter_obj, 0.0, True, 0.5, 0.5)


def on_nav_row_activated(window: Gtk.Window, treeview: Gtk.TreeView, path: Gtk.TreePath, column: Gtk.TreeViewColumn) -> None:
    """Handle a double-click in the navigator tree by scrolling to the item."""
    selection = treeview.get_selection()
    on_nav_selection_changed(window, selection)


def on_buffer_changed(buffer: Gtk.TextBuffer, tab_data: dict, window: Gtk.Window) -> None:
    """Track undo state and refresh the navigator when buffer contents change."""
    new_text = buffer.get_text(
        buffer.get_start_iter(), buffer.get_end_iter(), False
    )
    if tab_data.get('last_text') is None or tab_data['last_text'] != new_text:
        if tab_data.get('last_text') is not None:
            tab_data['undo_stack'].append(tab_data['last_text'])
        tab_data['last_text'] = new_text
    tab_data['modified'] = True
    update_navigator(window)
