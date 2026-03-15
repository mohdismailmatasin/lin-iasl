"""
Lin-IASL - ACPI Table Editor for Linux

A GTK3-based graphical editor for ACPI (Advanced Configuration and Power Interface)
source code and tables. Provides decompilation, compilation, and extraction of ACPI
tables from the system firmware.
"""

import gi
gi.require_version('Gtk', '3.0')

import os
import re
import subprocess
import sys
import tempfile
import threading
from typing import Optional, Dict, List, Any

from gi.repository import Gtk, Gdk, Pango, GLib

# internal modules
from . import search, tabs, dialogs

try:
    gi.require_version('GtkSource', '4')
    from gi.repository import GtkSource
    HAS_GTKSOURCE = True
except (ValueError, ImportError):
    HAS_GTKSOURCE = False
    GtkSource = None


# Configuration constants
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
NAVIGATOR_WIDTH = 200
TAB_HEADER_SPACING = 2
MONOSPACE_FONT_SIZE = 12
ACPI_TABLES_DIR = '/sys/firmware/acpi/tables'
OUTPUT_DIR_NAME = 'ACPI'
TIMEOUT_SECONDS = 10


class LinIaslWindow(Gtk.Window):
    """Main application window for Lin-IASL editor."""

    def __init__(self) -> None:
        """Initialize the Lin-IASL window and all UI components."""
        super().__init__(title="Lin-IASL - ACPI Table Editor")
        self.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        
        self.tabs: List[Dict[str, Any]] = []
        self.iasl_path = "iasl"
        # visual preferences
        self.dark_theme = True  # start with dark editor theme
        
        # Accelerator group for keyboard shortcuts
        self.accel = Gtk.AccelGroup()
        
        # Notebook for managing multiple tabs
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.set_hexpand(True)
        self.notebook.set_vexpand(True)
        self.notebook.connect('switch-page', self._on_switch_page)
        
        # Main vertical box layout
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(main_vbox)
        
        # Create menu bar
        self._create_menu_bar(main_vbox)
        
        # Create toolbar
        toolbar = Gtk.Toolbar()
        self._create_toolbar(toolbar)
        main_vbox.pack_start(toolbar, False, False, 0)
        
        # Create horizontal paned layout with navigator and editor
        hpaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        hpaned.set_position(NAVIGATOR_WIDTH)
        
        # Navigator panel (left side)
        navigator_box = self._create_navigator_panel()
        hpaned.add(navigator_box)
        
        # Notebook editor (right side)
        hpaned.add(self.notebook)
        main_vbox.pack_start(hpaned, True, True, 0)
        
        # Status bar
        self.statusbar = Gtk.Label(label="Ready")
        main_vbox.pack_start(self.statusbar, False, False, 0)
        
        # Add initial empty tab
        self._add_new_tab()
    
    def _create_navigator_panel(self) -> Gtk.Frame:
        """Create the left-side navigator panel for object navigation."""
        navigator_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Navigator header
        nav_label = Gtk.Label(label="Navigator")
        nav_label.set_halign(Gtk.Align.START)
        nav_label.set_valign(Gtk.Align.CENTER)
        navigator_box.pack_start(nav_label, False, False, 5)
        
        # Filter entry for searching objects
        self.nav_filter_entry = Gtk.Entry()
        self.nav_filter_entry.set_placeholder_text("Filter…")
        self.nav_filter_entry.connect("changed", self._on_filter_changed)
        navigator_box.pack_start(self.nav_filter_entry, False, False, 5)
        
        # Navigator tree view
        self.nav_tree = Gtk.TreeView()
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Objects", renderer, text=0)
        self.nav_tree.append_column(column)
        
        # Store object name and file offset for navigation
        self.nav_store = Gtk.TreeStore(str, int)
        self.nav_filter = self.nav_store.filter_new(None)
        self.nav_filter.set_visible_func(self._nav_filter_func)
        self.nav_tree.set_model(self.nav_filter)
        
        # Connect selection signals
        self.nav_tree.get_selection().connect("changed", self._on_nav_selection_changed)
        self.nav_tree.connect("row-activated", self._on_nav_row_activated)
        
        # Scrolled window for tree view
        nav_scrolled = Gtk.ScrolledWindow()
        nav_scrolled.add(self.nav_tree)
        nav_scrolled.set_hexpand(True)
        nav_scrolled.set_vexpand(True)
        navigator_box.pack_start(nav_scrolled, True, True, 0)
        
        # Wrap in frame
        nav_frame = Gtk.Frame()
        nav_frame.add(navigator_box)
        return nav_frame
    
    def _create_menu_bar(self, parent_box: Gtk.Box) -> None:
        """Create the application menu bar with File, Edit, Search, Tools, and Help menus."""
        menu_bar = Gtk.MenuBar()
        parent_box.pack_start(menu_bar, False, False, 0)
        
        # File menu
        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem(label="File")
        file_item.set_submenu(file_menu)
        
        file_new = Gtk.MenuItem(label="New")
        file_new.connect("activate", self._on_new)
        file_menu.append(file_new)
        
        file_open = Gtk.MenuItem(label="Open")
        file_open.connect("activate", self._on_open)
        file_open.add_accelerator("activate", self.accel, ord('o'), Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        file_menu.append(file_open)
        
        file_open_dir = Gtk.MenuItem(label="Open Directory")
        file_open_dir.connect("activate", self._on_open_dir)
        file_menu.append(file_open_dir)
        
        file_menu.append(Gtk.SeparatorMenuItem())
        
        file_save = Gtk.MenuItem(label="Save")
        file_save.connect("activate", self._on_save)
        file_save.add_accelerator("activate", self.accel, ord('s'), Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        file_menu.append(file_save)
        
        file_save_as = Gtk.MenuItem(label="Save As")
        file_save_as.connect("activate", self._on_save_as)
        file_save_as.add_accelerator("activate", self.accel, ord('s'), 
                                     Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK, Gtk.AccelFlags.VISIBLE)
        file_menu.append(file_save_as)
        
        file_menu.append(Gtk.SeparatorMenuItem())
        
        file_close = Gtk.MenuItem(label="Close Tab")
        file_close.connect("activate", self._on_close_tab)
        file_menu.append(file_close)
        
        file_menu.append(Gtk.SeparatorMenuItem())
        
        file_quit = Gtk.MenuItem(label="Quit")
        file_quit.connect("activate", Gtk.main_quit)
        file_quit.add_accelerator("activate", self.accel, ord('q'), Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        file_menu.append(file_quit)
        
        menu_bar.append(file_item)
        
        # Edit menu
        edit_menu = Gtk.Menu()
        edit_item = Gtk.MenuItem(label="Edit")
        edit_item.set_submenu(edit_menu)
        
        edit_undo = Gtk.MenuItem(label="Undo")
        edit_undo.connect("activate", self._on_undo)
        edit_menu.append(edit_undo)
        
        edit_redo = Gtk.MenuItem(label="Redo")
        edit_redo.connect("activate", self._on_redo)
        edit_menu.append(edit_redo)
        
        edit_menu.append(Gtk.SeparatorMenuItem())
        
        edit_cut = Gtk.MenuItem(label="Cut")
        edit_cut.connect("activate", self._on_cut)
        edit_menu.append(edit_cut)
        
        edit_copy = Gtk.MenuItem(label="Copy")
        edit_copy.connect("activate", self._on_copy)
        edit_menu.append(edit_copy)
        
        edit_paste = Gtk.MenuItem(label="Paste")
        edit_paste.connect("activate", self._on_paste)
        edit_menu.append(edit_paste)
        
        edit_menu.append(Gtk.SeparatorMenuItem())
        
        edit_select_all = Gtk.MenuItem(label="Select All")
        edit_select_all.connect("activate", self._on_select_all)
        edit_menu.append(edit_select_all)
        
        menu_bar.append(edit_item)
        
        # Search menu
        search_menu = Gtk.Menu()
        search_item = Gtk.MenuItem(label="Search")
        search_item.set_submenu(search_menu)
        
        search_find = Gtk.MenuItem(label="Find")
        search_find.connect("activate", self._on_find)
        search_find.add_accelerator("activate", self.accel, ord('f'), Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        search_menu.append(search_find)

        # Replace menu item (full dialog with options)
        search_replace = Gtk.MenuItem(label="Replace")
        search_replace.connect("activate", self._on_replace)
        search_replace.add_accelerator("activate", self.accel, ord('h'), Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        search_menu.append(search_replace)
        
        menu_bar.append(search_item)
        
        # Tools menu
        tools_menu = Gtk.Menu()
        tools_item = Gtk.MenuItem(label="Tools")
        tools_item.set_submenu(tools_menu)
        
        tools_compile = Gtk.MenuItem(label="Compile")
        tools_compile.connect("activate", self._on_compile)
        tools_compile.add_accelerator("activate", self.accel, ord('b'), Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        tools_menu.append(tools_compile)
        
        tools_decompile = Gtk.MenuItem(label="Decompile")
        tools_decompile.connect("activate", self._on_decompile)
        tools_menu.append(tools_decompile)
        
        tools_menu.append(Gtk.SeparatorMenuItem())
        
        tools_extract = Gtk.MenuItem(label="Extract ACPI Tables")
        tools_extract.connect("activate", self._on_extract_acpi)
        tools_menu.append(tools_extract)
        
        tools_menu.append(Gtk.SeparatorMenuItem())
        
        tools_log = Gtk.MenuItem(label="Show Log")
        tools_log.connect("activate", self._on_show_log)
        tools_menu.append(tools_log)
        
        menu_bar.append(tools_item)
        
        # View menu
        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem(label="View")
        view_item.set_submenu(view_menu)
        
        if HAS_GTKSOURCE:
            self.view_line_numbers = Gtk.CheckMenuItem(label="Show Line Numbers")
            self.view_line_numbers.connect("toggled", self._on_toggle_line_numbers)
            view_menu.append(self.view_line_numbers)

        # theme toggle flips light/dark styling for the editor pane
        self.view_dark_theme = Gtk.CheckMenuItem(label="Dark Theme")
        self.view_dark_theme.set_active(self.dark_theme)
        self.view_dark_theme.connect("toggled", self._on_toggle_theme)
        view_menu.append(self.view_dark_theme)
        
        menu_bar.append(view_item)
        
        # Help menu
        help_menu = Gtk.Menu()
        help_item = Gtk.MenuItem(label="Help")
        help_item.set_submenu(help_menu)
        
        help_about = Gtk.MenuItem(label="About")
        help_about.connect("activate", self._on_about)
        help_menu.append(help_about)
        
        menu_bar.append(help_item)
    
    def _get_theme_css(self) -> Gtk.CssProvider:
        """Return a CSS provider according to the current dark_theme flag."""
        css = Gtk.CssProvider()
        if self.dark_theme:
            bg = "#1e1e1e"
            fg = "#d4d4d4"
            gutter_bg = "#ffffff"    # light gutter even on dark theme
            gutter_fg = "#000000"
        else:
            bg = "#ffffff"
            fg = "#000000"
            gutter_bg = "#ffffff"
            gutter_fg = "#000000"
        css_str = f"""
            textview {{ 
                font-family: monospace; 
                font-size: {MONOSPACE_FONT_SIZE}px; 
                background-color: {bg}; 
                color: {fg}; 
            }}
            GtkSourceView {{ background-color: {bg}; }}
            GtkSourceGutter {{ background-color: {gutter_bg}; color: {gutter_fg}; }}
        """
        css.load_from_data(css_str.encode('utf-8'))
        return css

    def _on_toggle_theme(self, menu_item: Gtk.CheckMenuItem) -> None:
        """Switch between dark and light editor themes."""
        self.dark_theme = menu_item.get_active()
        # update existing tabs' styling
        for tab in self.tabs:
            view = tab['view']
            view.get_style_context().add_provider(self._get_theme_css(), Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _create_toolbar(self, toolbar: Gtk.Toolbar) -> None:
        """Create the toolbar with common action buttons."""
        # New button
        new_btn = Gtk.ToolButton()
        new_btn.set_icon_name("document-new")
        new_btn.set_tooltip_text("New")
        new_btn.connect("clicked", self._on_new)
        toolbar.insert(new_btn, 0)
        
        # Open button
        open_btn = Gtk.ToolButton()
        open_btn.set_icon_name("document-open")
        open_btn.set_tooltip_text("Open")
        open_btn.connect("clicked", self._on_open)
        toolbar.insert(open_btn, 1)
        
        # Save button
        save_btn = Gtk.ToolButton()
        save_btn.set_icon_name("document-save")
        save_btn.set_tooltip_text("Save")
        save_btn.connect("clicked", self._on_save)
        toolbar.insert(save_btn, 2)
        
        toolbar.insert(Gtk.SeparatorToolItem(), 3)
        
        # Find button
        find_btn = Gtk.ToolButton()
        find_btn.set_icon_name("edit-find")
        find_btn.set_tooltip_text("Find")
        find_btn.connect("clicked", self._on_find)
        toolbar.insert(find_btn, 4)
        
        toolbar.insert(Gtk.SeparatorToolItem(), 5)
        
        # Compile button
        compile_btn = Gtk.ToolButton()
        compile_btn.set_icon_name("system-run")
        compile_btn.set_tooltip_text("Compile")
        compile_btn.connect("clicked", self._on_compile)
        toolbar.insert(compile_btn, 6)
    
    def _add_new_tab(self, file_path: Optional[str] = None, content: Optional[str] = None) -> Optional[int]:
        """
        Add a new editor tab to the notebook.
        
        Args:
            file_path: Path to file to open, if any
            content: Custom text content to display
            
        Returns:
            The notebook page number, or None on failure
        """
        # Create source view for editing (supports line numbers)
        if HAS_GTKSOURCE:
            text_view = GtkSource.View()
            text_buffer = GtkSource.Buffer()
        else:
            text_view = Gtk.TextView()
            text_buffer = Gtk.TextBuffer()
        
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        text_view.set_hexpand(True)
        text_view.set_vexpand(True)
        text_view.set_editable(True)
        text_view.set_cursor_visible(True)
        
        # Apply monospace font styling based on current theme
        css = self._get_theme_css()
        text_view.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        # Create syntax highlighting tags
        text_buffer.create_tag("keyword", foreground="blue", weight=Pango.Weight.BOLD)
        text_buffer.create_tag("function", foreground="darkgreen", weight=Pango.Weight.BOLD)
        text_buffer.create_tag("string", foreground="red")
        text_buffer.create_tag("comment", foreground="gray")
        text_buffer.create_tag("number", foreground="purple")
        text_buffer.create_tag("operator", foreground="orange")
        
        # Load content
        if content:
            text_buffer.set_text(content)
        elif file_path:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    data = f.read()
                text_buffer.set_text(data)
            except Exception as e:
                self._show_error(f"Failed to load: {e}")
                return None
        else:
            text_buffer.set_text("")
        
        text_view.set_buffer(text_buffer)
        
        # Scrolled window
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.add(text_view)
        
        # Create tab header with close button
        tab_name = os.path.basename(file_path) if file_path else "Untitled"
        tab_header = self._create_tab_header(tab_name)
        
        # Add page to notebook
        page_num = self.notebook.append_page(scrolled_window, tab_header)
        self.notebook.set_current_page(page_num)
        scrolled_window.show_all()
        tab_header.show_all()
        
        # Store tab data
        tab_data = {
            'view': text_view,
            'buffer': text_buffer,
            'file_path': file_path,
            'modified': False,
            'undo_stack': [],
            'redo_stack': [],
            'last_text': text_buffer.get_text(text_buffer.get_start_iter(), text_buffer.get_end_iter(), False),
            'header': tab_header
        }
        
        self.tabs.append(tab_data)
        text_buffer.connect('changed', self._on_buffer_changed, tab_data)
        
        # Update navigator for new tab
        self._update_navigator()
        return page_num
    
    def _get_current_tab(self) -> Optional[Dict[str, Any]]:
        """Get the currently active tab data."""
        page = self.notebook.get_current_page()
        if 0 <= page < len(self.tabs):
            return self.tabs[page]
        return None

    def _on_switch_page(self, notebook: Gtk.Notebook, page: Gtk.Widget, page_num: int) -> None:
        """Handle page switch event - update navigator for new page."""
        self._update_navigator()

    def _create_tab_header(self, name: str) -> Gtk.Box:
        """Create a tab header widget with label and close button."""
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=TAB_HEADER_SPACING)
        label = Gtk.Label(label=name)
        close_btn = Gtk.Button()
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.set_focus_on_click(False)
        close_icon = Gtk.Image.new_from_icon_name("window-close", Gtk.IconSize.MENU)
        close_btn.add(close_icon)
        header_box.pack_start(label, True, True, 0)
        header_box.pack_start(close_btn, False, False, 0)
        close_btn.connect("clicked", self._on_close_button_clicked, header_box)
        return header_box

    def _on_close_button_clicked(self, button: Gtk.Button, header: Gtk.Box) -> None:
        """Handle close button click - close the associated tab."""
        for i in range(self.notebook.get_n_pages()):
            if self.notebook.get_tab_label(self.notebook.get_nth_page(i)) is header:
                self._close_page(i)
                break

    def _close_page(self, index: int) -> None:
        """Close a tab by index."""
        if 0 <= index < len(self.tabs):
            self.notebook.remove_page(index)
            self.tabs.pop(index)
            self._update_navigator()
    
    def _update_navigator(self) -> None:
        from .tabs import update_navigator
        update_navigator(self)

    def _apply_syntax_highlighting(self, text_buffer, buffer_text: str) -> None:
        from .tabs import apply_syntax_highlighting
        apply_syntax_highlighting(text_buffer, buffer_text)

    def _nav_filter_func(self, model: Gtk.TreeModel, tree_iter: Gtk.TreeIter, data: Any = None) -> bool:
        from .tabs import nav_filter_func
        return nav_filter_func(model, tree_iter, data)

    def _on_filter_changed(self, entry: Gtk.Entry) -> None:
        from .tabs import on_filter_changed
        on_filter_changed(self, entry)

    def _on_nav_selection_changed(self, selection: Gtk.TreeSelection) -> None:
        from .tabs import on_nav_selection_changed
        on_nav_selection_changed(self, selection)

    def _on_nav_row_activated(self, treeview: Gtk.TreeView, path: Gtk.TreePath, column: Gtk.TreeViewColumn) -> None:
        from .tabs import on_nav_row_activated
        on_nav_row_activated(self, treeview, path, column)
    
    def _on_buffer_changed(self, buffer, tab_data: Dict[str, Any]) -> None:
        from .tabs import on_buffer_changed
        on_buffer_changed(buffer, tab_data, self)
    
    def _on_new(self, *args: Any) -> None:
        """Create a new empty document."""
        self._add_new_tab()
        self.statusbar.set_text("New file")
    
    def _on_open(self, *args: Any) -> None:
        """Open a file dialog and load selected file."""
        dialog = Gtk.FileChooserDialog(
            title="Open File", parent=self, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(Gtk.STOCK_OPEN, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        
        # ASL/DSL filter
        asl_filter = Gtk.FileFilter()
        asl_filter.set_name("ASL/DSL Files")
        asl_filter.add_pattern("*.dsl")
        asl_filter.add_pattern("*.DSL")
        asl_filter.add_pattern("*.asl")
        asl_filter.add_pattern("*.ASL")
        dialog.add_filter(asl_filter)
        
        # AML filter
        aml_filter = Gtk.FileFilter()
        aml_filter.set_name("AML Files")
        aml_filter.add_pattern("*.aml")
        aml_filter.add_pattern("*.AML")
        dialog.add_filter(aml_filter)
        
        # All files filter
        all_filter = Gtk.FileFilter()
        all_filter.set_name("All Files")
        all_filter.add_pattern("*")
        dialog.add_filter(all_filter)
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_path = dialog.get_filename()
            dialog.destroy()
            
            # If AML file, decompile it first
            if file_path.lower().endswith('.aml'):
                output_path = os.path.splitext(file_path)[0] + ".dsl"
                try:
                    result = subprocess.run(
                        [self.iasl_path, "-p", output_path, "-d", file_path],
                        capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        self.statusbar.set_text(f"Decompiled: {output_path}")
                        file_path = output_path  # Open the DSL instead
                    else:
                        self._show_error(f"Decompile failed:\n{result.stderr}")
                        return
                except FileNotFoundError:
                    self._show_error("iasl not found")
                    return
            
            # If only one empty tab, replace it
            if (len(self.tabs) == 1 and not self.tabs[0]['file_path'] and
                self.tabs[0]['buffer'].get_text(
                    self.tabs[0]['buffer'].get_start_iter(),
                    self.tabs[0]['buffer'].get_end_iter(), False
                ) == ""):
                self._close_page(0)
            
            self._add_new_tab(file_path=file_path)
            self.statusbar.set_text(f"Opened: {os.path.basename(file_path)}")
        else:
            dialog.destroy()
    
    def _on_open_dir(self, *args: Any) -> None:
        """Open multiple ACPI files from a directory."""
        dialog = Gtk.FileChooserDialog(
            title="Open Directory", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(Gtk.STOCK_OPEN, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        
        if dialog.run() == Gtk.ResponseType.OK:
            dir_path = dialog.get_filename()
            dialog.destroy()
            count = 0
            for file_name in sorted(os.listdir(dir_path)):
                if file_name.lower().endswith(('.dsl', '.asl', '.aml')):
                    self._add_new_tab(file_path=os.path.join(dir_path, file_name))
                    count += 1
            self.statusbar.set_text(f"Opened {count} files")
        else:
            dialog.destroy()
    
    def _on_save(self, *args: Any) -> None:
        """Save current document."""
        tab = self._get_current_tab()
        if not tab:
            return
        
        if tab['file_path']:
            self._save_to_file(tab, tab['file_path'])
        else:
            self._on_save_as()
    
    def _on_save_as(self, *args: Any) -> None:
        """Save document with a new name/location."""
        tab = self._get_current_tab()
        if not tab:
            return
        
        dialog = Gtk.FileChooserDialog(
            title="Save File", parent=self, action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons(Gtk.STOCK_SAVE, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dialog.set_current_name("untitled.dsl")
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_path = dialog.get_filename()
            dialog.destroy()
            self._save_to_file(tab, file_path)
        else:
            dialog.destroy()
    
    def _save_to_file(self, tab: Dict[str, Any], file_path: str) -> None:
        """Save tab content to file and update tab header."""
        try:
            content = tab['buffer'].get_text(
                tab['buffer'].get_start_iter(),
                tab['buffer'].get_end_iter(), False
            )
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            tab['file_path'] = file_path
            tab['modified'] = False
            self.statusbar.set_text(f"Saved: {file_path}")
            
            # Update tab header label
            if 'header' in tab:
                children = tab['header'].get_children()
                if children and isinstance(children[0], Gtk.Label):
                    children[0].set_text(os.path.basename(file_path))
        except Exception as e:
            self._show_error(f"Save failed: {e}")
    
    def _on_close_tab(self, *args: Any) -> None:
        """Close the current tab."""
        page = self.notebook.get_current_page()
        if page >= 0:
            self._close_page(page)
    
    def _on_undo(self, *args: Any) -> None:
        """Undo last text change."""
        tab = self._get_current_tab()
        if not tab or not tab['undo_stack']:
            return
        current = tab['buffer'].get_text(
            tab['buffer'].get_start_iter(),
            tab['buffer'].get_end_iter(), False
        )
        tab['redo_stack'].append(current)
        previous = tab['undo_stack'].pop()
        tab['buffer'].set_text(previous)
        tab['last_text'] = previous
    
    def _on_redo(self, *args: Any) -> None:
        """Redo undone text change."""
        tab = self._get_current_tab()
        if not tab or not tab['redo_stack']:
            return
        current = tab['buffer'].get_text(
            tab['buffer'].get_start_iter(),
            tab['buffer'].get_end_iter(), False
        )
        tab['undo_stack'].append(current)
        next_text = tab['redo_stack'].pop()
        tab['buffer'].set_text(next_text)
        tab['last_text'] = next_text
    
    def _on_cut(self, *args: Any) -> None:
        """Cut selected text (delegate to GtkTextView)."""
        tab = self._get_current_tab()
        if tab:
            tab['view'].emit('cut-clipboard')
    
    def _on_copy(self, *args: Any) -> None:
        """Copy selected text (delegate to GtkTextView)."""
        tab = self._get_current_tab()
        if tab:
            tab['view'].emit('copy-clipboard')
    
    def _on_paste(self, *args: Any) -> None:
        """Paste text from clipboard (delegate to GtkTextView)."""
        tab = self._get_current_tab()
        if tab:
            tab['view'].emit('paste-clipboard')
    
    def _on_select_all(self, *args: Any) -> None:
        """Select all text in current document."""
        tab = self._get_current_tab()
        if tab:
            tab['buffer'].select_range(
                tab['buffer'].get_start_iter(),
                tab['buffer'].get_end_iter()
            )
    
    # wrappers that delegate searching/highlighting logic to the search module
    def _search_buffer(self,
                       buffer: Gtk.TextBuffer,
                       text: str,
                       start_iter: Gtk.TextIter,
                       forward: bool = True,
                       case_sensitive: bool = False,
                       regex: bool = False,
                       word_only: bool = False) -> Optional[tuple]:
        from .search import search_buffer
        return search_buffer(buffer, text, start_iter, forward,
                             case_sensitive=case_sensitive,
                             regex=regex, word_only=word_only)

    def _highlight_all_matches(self,
                               buffer: Gtk.TextBuffer,
                               text: str,
                               case_sensitive: bool = False,
                               regex: bool = False,
                               word_only: bool = False) -> None:
        from .search import highlight_all_matches
        highlight_all_matches(buffer, text,
                              case_sensitive=case_sensitive,
                              regex=regex, word_only=word_only)

    def _clear_highlights(self, buffer: Gtk.TextBuffer) -> None:
        from .search import clear_highlights
        clear_highlights(buffer)

    def _create_search_dialog(self, replace: bool = False) -> Gtk.Dialog:
        from .search import create_search_dialog
        return create_search_dialog(self, replace=replace)

    def _on_find(self, *args: Any) -> None:
        """Bring up the find dialog and locate the first occurrence."""
        tab = self._get_current_tab()
        if tab:
            # clear any previous highlights before new search
            self._clear_highlights(tab['buffer'])

        dialog = self._create_search_dialog(replace=False)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            search_text = dialog._find_entry.get_text()
            if search_text and tab:
                buf = tab['buffer']
                start = buf.get_start_iter()
                flags = {
                    'case_sensitive': dialog._case_cb.get_active(),
                    'regex': dialog._regex_cb.get_active(),
                    'word_only': dialog._word_cb.get_active(),
                }
                match = self._search_buffer(buf, search_text, start, True,
                                            **flags)
                if match:
                    s, e = match
                    buf.select_range(s, e)
                    tab['view'].scroll_to_iter(s, 0.0, True, 0.5, 0.5)
                    # highlight all matches for convenience
                    self._highlight_all_matches(buf, search_text, **flags)
        dialog.destroy()

    def _on_replace(self, *args: Any) -> None:
        """Show a combined find/replace dialog and handle all of the button
        actions (find next, replace, replace all)."""
        tab = self._get_current_tab()
        if tab:
            self._clear_highlights(tab['buffer'])
        dialog = self._create_search_dialog(replace=True)
        while True:
            response = dialog.run()
            if response == Gtk.ResponseType.CANCEL or response == Gtk.ResponseType.DELETE_EVENT:
                break

            search_text = dialog._find_entry.get_text()
            replace_text = dialog._replace_entry.get_text() if dialog._replace_entry else ""
            flags = {
                'case_sensitive': dialog._case_cb.get_active(),
                'regex': dialog._regex_cb.get_active(),
                'word_only': dialog._word_cb.get_active(),
            }

            tab = self._get_current_tab()
            if not tab or not search_text:
                continue
            buf = tab['buffer']

            if response == Gtk.ResponseType.OK:  # find next
                # start from end of current selection or beginning
                start = buf.get_selection_bounds()[1] if buf.get_has_selection() else buf.get_start_iter()
                match = self._search_buffer(buf, search_text, start, True, **flags)
                if match:
                    s, e = match
                    buf.select_range(s, e)
                    tab['view'].scroll_to_iter(s, 0.0, True, 0.5, 0.5)
                    self._highlight_all_matches(buf, search_text, **flags)
            elif response == Gtk.ResponseType.APPLY:  # replace
                bounds = buf.get_selection_bounds()
                if bounds:
                    s, e = bounds
                    # ensure selected text actually matches search pattern
                    sel_text = buf.get_text(s, e, False)
                    if sel_text:
                        if (flags['regex'] and re.fullmatch(search_text, sel_text)) or (sel_text == search_text) or (not flags['case_sensitive'] and sel_text.lower() == search_text.lower()):
                            buf.delete(s, e)
                            buf.insert(s, replace_text)
                # after replacing, move to next match
                start = buf.get_iter_at_mark(buf.get_insert())
                match = self._search_buffer(buf, search_text, start, True, **flags)
                if match:
                    s, e = match
                    buf.select_range(s, e)
                    tab['view'].scroll_to_iter(s, 0.0, True, 0.5, 0.5)
                    self._highlight_all_matches(buf, search_text, **flags)
            elif response == Gtk.ResponseType.YES:  # replace all
                count = 0
                iter_ = buf.get_start_iter()
                while True:
                    match = self._search_buffer(buf, search_text, iter_, True, **flags)
                    if not match:
                        break
                    s, e = match
                    buf.delete(s, e)
                    buf.insert(s, replace_text)
                    count += 1
                    iter_ = buf.get_iter_at_offset(s.get_offset() + len(replace_text))
                self.statusbar.set_text(f"Replaced {count} occurrences")
                self._highlight_all_matches(buf, search_text, **flags)
        dialog.destroy()
    
    def _on_compile(self, *args: Any) -> None:
        """Compile the current ASL/DSL file to AML bytecode."""
        tab = self._get_current_tab()
        if not tab:
            return
        
        # Get content
        content = tab['buffer'].get_text(
            tab['buffer'].get_start_iter(),
            tab['buffer'].get_end_iter(), False
        )
        
        # Use existing file or create temporary file
        if tab['file_path']:
            self._on_save()
            source_path = tab['file_path']
            is_temp = False
        else:
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.dsl')
            tmp_file.write(content.encode('utf-8'))
            tmp_file.close()
            source_path = tmp_file.name
            is_temp = True
        
        output_path = os.path.splitext(source_path)[0] + ".aml"
        
        try:
            result = subprocess.run(
                [self.iasl_path, "-p", output_path, source_path],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                self.statusbar.set_text(f"Compiled: {output_path}")
                self._add_new_tab(file_path=output_path)
            else:
                self._show_error(f"Compile failed:\n{result.stderr}")
        except FileNotFoundError:
            self._show_error("iasl not found. Install: sudo apt install acpica-tools")
        finally:
            if is_temp:
                os.unlink(source_path)
    
    def _on_decompile(self, *args: Any) -> None:
        """Open AML file and decompile to ASL/DSL."""
        dialog = Gtk.FileChooserDialog(
            title="Decompile AML", parent=self, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(Gtk.STOCK_OPEN, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        
        aml_filter = Gtk.FileFilter()
        aml_filter.set_name("AML Files")
        aml_filter.add_pattern("*.aml")
        dialog.add_filter(aml_filter)
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            aml_path = dialog.get_filename()
            dialog.destroy()
            dsl_path = os.path.splitext(aml_path)[0] + ".dsl"
            
            try:
                result = subprocess.run(
                    [self.iasl_path, "-p", dsl_path, "-d", aml_path],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    self.statusbar.set_text(f"Decompiled: {dsl_path}")
                    self._add_new_tab(file_path=dsl_path)
                else:
                    self._show_error(f"Failed:\n{result.stderr}")
            except FileNotFoundError:
                self._show_error("iasl not found")
        else:
            dialog.destroy()
    
    def _on_extract_acpi(self, *args: Any) -> None:
        """Extract ACPI tables from system firmware."""
        if not os.path.exists(ACPI_TABLES_DIR):
            self._show_error("ACPI tables not accessible.")
            return
        
        tables = [f for f in os.listdir(ACPI_TABLES_DIR) if not f.startswith('.')]
        
        if not tables:
            self._show_error("No tables found.")
            return
        
        # Create dialog to show available tables
        dialog = Gtk.Dialog(title="Extract Tables", parent=self, flags=0)
        dialog.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        
        model = Gtk.ListStore(str)
        for table in sorted(tables):
            model.append([table])
        
        tree_view = Gtk.TreeView(model=model)
        renderer = Gtk.CellRendererText()
        tree_view.append_column(Gtk.TreeViewColumn("Table", renderer, text=0))
        
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.add(tree_view)
        scrolled_window.set_size_request(300, 400)
        dialog.get_content_area().add(scrolled_window)
        
        dialog.show_all()
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            # Prepare output directory
            project_dir = os.path.abspath(os.getcwd())
            output_dir = os.path.join(project_dir, OUTPUT_DIR_NAME)
            
            # Fix permissions if directory exists
            self._fix_acpi_permissions(output_dir)
            
            # Ensure directory and permissions are correct
            os.makedirs(output_dir, exist_ok=True)
            os.chmod(output_dir, 0o755)
            
            if os.path.exists(output_dir):
                for root, dirs, files in os.walk(output_dir):
                    for d in dirs:
                        os.chmod(os.path.join(root, d), 0o755)
                    for f in files:
                        os.chmod(os.path.join(root, f), 0o644)
            
            # Extract all tables
            selected_tables = tables
            
            # Build extraction command
            self._run_extract_async(output_dir, selected_tables)
        
        dialog.destroy()
    
    def _fix_acpi_permissions(self, output_dir: str) -> None:
        """
        Fix permissions on existing ACPI directory.
        
        Args:
            output_dir: Path to the ACPI output directory
        """
        if not os.path.exists(output_dir):
            return
        
        try:
            current_user = os.environ.get('USER', os.environ.get('LOGNAME', 'user'))
            
            # Try pkexec first
            result = subprocess.run(
                ['pkexec', 'sh', '-c', 
                 f"chown -R {current_user}:{current_user} '{output_dir}' && chmod -R u+rwX '{output_dir}'"],
                capture_output=True, text=True, timeout=TIMEOUT_SECONDS
            )
            
            if result.returncode != 0:
                # Fallback to sudo
                subprocess.run(
                    ['sudo', 'chown', '-R', f"{current_user}:{current_user}", output_dir],
                    capture_output=True, text=True, timeout=TIMEOUT_SECONDS
                )
                subprocess.run(
                    ['sudo', 'chmod', '-R', 'u+rwX', output_dir],
                    capture_output=True, text=True, timeout=TIMEOUT_SECONDS
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Ignore if tools not available
    
    def _run_extract_async(self, output_dir: str, selected_tables: List[str]) -> None:
        """
        Run ACPI table extraction asynchronously in a background thread.
        
        Args:
            output_dir: Output directory path
            selected_tables: List of table names to extract
        """
        output_dir_quoted = output_dir.replace("'", "'\\''")
        tables_list = " ".join(selected_tables)
        current_user = os.environ.get('USER', os.environ.get('LOGNAME', 'user'))
        
        command = (
            f"for t in {tables_list}; do "
            f"cp '{ACPI_TABLES_DIR}/'$t '{output_dir_quoted}'/$t.aml && "
            f"iasl -d '{output_dir_quoted}'/$t.aml && "
            f"rm '{output_dir_quoted}'/$t.aml; done && "
            f"chown -R {current_user}:{current_user} '{output_dir_quoted}' && "
            f"chmod -R u+rwX '{output_dir_quoted}'"
        )
        
        def run_extract() -> None:
            """Run extraction with pkexec."""
            try:
                result = subprocess.run(
                    ['pkexec', 'sh', '-c', command],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    message = f"Extracted {len(selected_tables)} tables to: {output_dir}"
                    GLib.idle_add(lambda: self.statusbar.set_text(message))
                else:
                    error_msg = f"Extraction failed:\n{result.stderr}"
                    GLib.idle_add(lambda: self._show_error(error_msg))
            except Exception as e:
                error_msg = f"Extraction failed: {e}"
                GLib.idle_add(lambda: self._show_error(error_msg))
        
        thread = threading.Thread(target=run_extract)
        thread.start()
    

    def _on_show_log(self, *args: Any) -> None:
        """Show iasl help/log information."""
        dialog = Gtk.Dialog(title="Log", parent=self, flags=0)
        dialog.set_default_size(600, 400)
        dialog.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        
        try:
            result = subprocess.run(
                [self.iasl_path, "-h"],
                capture_output=True, text=True, timeout=TIMEOUT_SECONDS
            )
            text_view.get_buffer().set_text(result.stdout)
        except FileNotFoundError:
            text_view.get_buffer().set_text(
                "iasl not found.\n\nInstall: sudo apt install acpica-tools"
            )
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        scrolled.add(text_view)
        dialog.get_content_area().add(scrolled)
        dialog.run()
        dialog.destroy()
    
    def _on_toggle_line_numbers(self, menu_item: Gtk.CheckMenuItem) -> None:
        """Toggle line numbers display in all editor tabs."""
        if not HAS_GTKSOURCE:
            return
        
        show_line_numbers = menu_item.get_active()
        
        for tab in self.tabs:
            text_view = tab['view']
            if show_line_numbers:
                self._enable_line_numbers(text_view)
            else:
                self._disable_line_numbers(text_view)
        
        self.statusbar.set_text(f"Line numbers {'enabled' if show_line_numbers else 'disabled'}")
    
    def _enable_line_numbers(self, text_view) -> None:
        """Enable line numbers display for a text view."""
        if HAS_GTKSOURCE and hasattr(text_view, 'set_show_line_numbers'):
            text_view.set_show_line_numbers(True)
    
    def _disable_line_numbers(self, text_view) -> None:
        """Disable line numbers display for a text view."""
        if HAS_GTKSOURCE and hasattr(text_view, 'set_show_line_numbers'):
            text_view.set_show_line_numbers(False)
    
    def _on_about(self, *args: Any) -> None:
        from .dialogs import show_about
        show_about(self)
    
    def _show_error(self, message: str) -> None:
        from .dialogs import show_error
        show_error(self, message)
        error_dialog = Gtk.MessageDialog(
            parent=self, flags=0, type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=message
        )
        error_dialog.run()
        error_dialog.destroy()


def main() -> None:
    """Entry point for the Lin-IASL application."""
    window = LinIaslWindow()
    window.connect("destroy", Gtk.main_quit)
    window.add_accel_group(window.accel)
    
    # Load file from command line argument if provided
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        # Remove initial empty tab
        if window.notebook.get_n_pages() > 0:
            window.notebook.remove_page(0)
            window.tabs.clear()
        window._add_new_tab(file_path=sys.argv[1])
    
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
