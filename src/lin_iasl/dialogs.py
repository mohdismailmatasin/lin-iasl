from gi.repository import Gtk


def show_error(parent: Gtk.Window, message: str) -> None:
    """Show an error message dialog attached to |parent|."""
    error_dialog = Gtk.MessageDialog(
        parent=parent, flags=0, type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK, text=message
    )
    error_dialog.run()
    error_dialog.destroy()


def show_about(parent: Gtk.Window) -> None:
    """Display the 'About' dialog for the application."""
    about_dialog = Gtk.AboutDialog()
    about_dialog.set_program_name("Lin-IASL")
    about_dialog.set_version("1.0.0")
    about_dialog.set_comments("ACPI Table Editor for Linux")
    about_dialog.set_authors(["Lin-IASL Contributors"])
    about_dialog.set_copyright("Copyright © 2024 Lin-IASL")
    about_dialog.set_website_label("Contact")
    about_dialog.set_website("mailto:mohdismailmatasin@gmail.com")
    about_dialog.run()
    about_dialog.destroy()
