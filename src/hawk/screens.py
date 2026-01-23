from typing import Optional

from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static, Button, ListView, ListItem, Label
from textual.containers import Vertical, Horizontal

from hawk.db import Client, get_all_clients


class DeleteClientScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    DeleteClientScreen { align: center middle; }
    #delete-dialog { width: 45; height: 8; border: thick $accent; background: $surface; padding: 1 2; }
    #delete-title { text-align: center; text-style: bold; padding-bottom: 1; }
    Horizontal { align: center middle; }
    Button { margin: 0 1; }
    """

    def __init__(self, client_name: str) -> None:
        super().__init__()
        self.client_name = client_name

    def compose(self):
        with Vertical(id="delete-dialog"):
            yield Static(f"Delete {self.client_name}?", id="delete-title")
            with Horizontal():
                yield Button("Delete", id="yes", variant="error")
                yield Button("Cancel", id="no", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class LinkClientScreen(ModalScreen[Optional[str]]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    LinkClientScreen { align: center middle; }
    #link-dialog { width: 50; height: 16; border: thick $accent; background: $surface; padding: 1 2; }
    #link-title { text-align: center; text-style: bold; padding-bottom: 1; }
    ListView { height: 8; border: solid $primary; }
    Horizontal { align: center middle; padding-top: 1; }
    Button { margin: 0 1; }
    """

    def __init__(
        self, project_name: str, current_client_id: Optional[str] = None
    ) -> None:
        super().__init__()
        self.project_name = project_name
        self.current_client_id = current_client_id
        self.clients = get_all_clients()
        self.selected_id: Optional[str] = current_client_id

    def compose(self):
        with Vertical(id="link-dialog"):
            yield Static(f"Link {self.project_name} to client", id="link-title")
            lv = ListView()
            lv.append(ListItem(Label("(No client)"), id="client-none"))
            for c in self.clients:
                lv.append(
                    ListItem(
                        Label(f"{c.name} ({c.company})" if c.company else c.name),
                        id=f"client-{c.id}",
                    )
                )
            yield lv
            with Horizontal():
                yield Button("Link", id="link", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and event.item.id:
            if event.item.id == "client-none":
                self.selected_id = None
            else:
                self.selected_id = event.item.id.replace("client-", "")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "link":
            self.dismiss(self.selected_id)
        else:
            self.dismiss(self.current_client_id)

    def action_cancel(self) -> None:
        self.dismiss(self.current_client_id)


class HealthCheckScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("c", "dismiss", "Close", show=False),
    ]

    CSS = """
    HealthCheckScreen { layout: vertical; align: center middle; background: rgba(0, 0, 0, 0.6); }
    #health-dialog { width: 70; height: auto; border: solid #fabd2f; background: #282828; padding: 1 2; }
    #health-title { text-style: bold; color: #fabd2f; }
    """

    def compose(self):
        with Vertical(id="health-dialog"):
            yield Static("Health Check (runs on startup)", id="health-title")
            yield Static("")
            yield Static("Checks each project in ~/ai/projects/ for:")
            yield Static("")
            yield Static("  [green]•[/green] project.md, session.md, gotchas.md exist")
            yield Static("  [green]•[/green] session.md updated within 7 days")
            yield Static("  [green]•[/green] Repo: path defined in project.md")
            yield Static("  [green]•[/green] Repo path actually exists on disk")
            yield Static("  [green]•[/green] CLAUDE.md symlink exists in repo")
            yield Static("  [green]•[/green] AGENTS.md exists in repo")
            yield Static("")
            yield Static("[dim]Press Esc to close[/dim]")
