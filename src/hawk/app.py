"""Main hawk-tui application."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Static


class ProjectList(Static):
    """Left panel: list of projects."""

    def compose(self) -> ComposeResult:
        yield Static("● project1\n○ project2\n○ project3", id="project-items")


class DetailPanel(Static):
    """Right panel: project details."""

    def compose(self) -> ComposeResult:
        yield Static("Select a project to view details", id="detail-content")


class AlertsPanel(Static):
    """Bottom panel: alerts and warnings."""

    def compose(self) -> ComposeResult:
        yield Static("No alerts", id="alerts-content")


class HawkApp(App):
    """Main hawk-tui application."""

    TITLE = "hawk-tui"
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-rows: 1fr auto;
    }

    #projects {
        width: 20;
        border: solid green;
        padding: 1;
    }

    #details {
        border: solid green;
        padding: 1;
    }

    #alerts {
        column-span: 2;
        height: 3;
        border: solid yellow;
        padding: 0 1;
    }

    Footer {
        column-span: 2;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f1", "help", "Help"),
        Binding("c", "check", "Check"),
        Binding("s", "sync", "Sync"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield ProjectList(id="projects")
        yield DetailPanel(id="details")
        yield AlertsPanel(id="alerts")
        yield Footer()

    def action_help(self) -> None:
        """Show help screen."""
        self.notify("Help: Press q to quit, Enter to start session")

    def action_check(self) -> None:
        """Run integrity check."""
        self.notify("Integrity check... (not implemented yet)")

    def action_sync(self) -> None:
        """Sync projects from ~/ai/projects."""
        self.notify("Syncing projects... (not implemented yet)")


def main():
    """Entry point for hawk-tui."""
    app = HawkApp()
    app.run()


if __name__ == "__main__":
    main()
