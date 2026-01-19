from typing import Optional

from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Input, ListView, ListItem, Label
from textual.containers import Vertical, Horizontal

from hawk.db import Client, get_all_clients


class RepoPathScreen(ModalScreen[str]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "submit", "Save", show=False),
    ]

    CSS = """
    RepoPathScreen { align: center middle; }
    #repo-dialog { width: 60; height: 10; border: thick $accent; background: $surface; padding: 1 2; }
    #repo-title { text-align: center; text-style: bold; padding-bottom: 1; }
    Input { margin: 1 0; }
    Horizontal { align: center middle; }
    Button { margin: 0 1; }
    """

    def __init__(self, project: str) -> None:
        super().__init__()
        self.project = project

    def compose(self):
        with Vertical(id="repo-dialog"):
            yield Static(f"Enter repo path for {self.project}", id="repo-title")
            yield Input(placeholder="~/Works/project-name", id="repo-input")
            with Horizontal():
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.dismiss(self.query_one("#repo-input", Input).value)
        else:
            self.dismiss("")

    def action_cancel(self) -> None:
        self.dismiss("")

    def action_submit(self) -> None:
        save_button = self.query_one("#save", Button)
        self.on_button_pressed(Button.Pressed(save_button))


class ClientFormScreen(ModalScreen[Optional[Client]]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "submit", "Save", show=False),
    ]

    CSS = """
    ClientFormScreen { align: center middle; }
    #client-dialog { width: 75; height: 40; border: thick $accent; background: $surface; padding: 1 2; }
    #client-title { text-align: center; text-style: bold; padding-bottom: 1; }
    .field-row { height: 3; }
    .field-label { width: 14; padding-top: 1; }
    .field-input { width: 1fr; }
    .section-title { text-style: bold; color: $accent; padding-top: 1; }
    #button-row { padding-top: 1; }
    #button-row Button { margin: 0 1; }
    """

    def __init__(self, client: Optional[Client] = None) -> None:
        super().__init__()
        self.client = client

    def compose(self):
        from datetime import datetime

        title = "Edit Client" if self.client else "Add Client"
        with Vertical(id="client-dialog"):
            yield Static(title, id="client-title")
            with Horizontal(classes="field-row"):
                yield Static("ID (slug):", classes="field-label")
                yield Input(
                    value=self.client.id if self.client else "",
                    id="client-id",
                    classes="field-input",
                    disabled=bool(self.client),
                )
            with Horizontal(classes="field-row"):
                yield Static("Name:", classes="field-label")
                yield Input(
                    value=self.client.name if self.client else "",
                    id="name",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Static("Company:", classes="field-label")
                yield Input(
                    value=self.client.company if self.client else "",
                    id="company",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Static("Email:", classes="field-label")
                yield Input(
                    value=self.client.email if self.client else "",
                    id="email",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Static("Phone:", classes="field-label")
                yield Input(
                    value=self.client.phone if self.client else "",
                    id="phone",
                    classes="field-input",
                )
            yield Static("Billing", classes="section-title")
            with Horizontal(classes="field-row"):
                yield Static("Cycle:", classes="field-label")
                yield Input(
                    value=self.client.billing_cycle if self.client else "annual",
                    id="billing-cycle",
                    classes="field-input",
                    placeholder="annual / monthly / one-time",
                )
            with Horizontal(classes="field-row"):
                yield Static("Amount:", classes="field-label")
                yield Input(
                    value=str(self.client.amount) if self.client else "0",
                    id="amount",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Static("Next Payment:", classes="field-label")
                yield Input(
                    value=self.client.next_payment if self.client else "",
                    id="next-payment",
                    classes="field-input",
                    placeholder="YYYY-MM-DD",
                )
            with Horizontal(classes="field-row"):
                yield Static("Notes:", classes="field-label")
                yield Input(
                    value=self.client.notes if self.client else "",
                    id="notes",
                    classes="field-input",
                )
            with Horizontal(id="button-row"):
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        from datetime import datetime

        if event.button.id == "save":
            client_id = self.query_one("#client-id", Input).value.strip()
            name = self.query_one("#name", Input).value.strip()
            if not client_id or not name:
                self.app.notify("ID and Name are required")
                return
            try:
                amount = int(self.query_one("#amount", Input).value.strip() or "0")
            except ValueError:
                amount = 0
            next_payment_str = self.query_one("#next-payment", Input).value.strip()
            if next_payment_str:
                try:
                    datetime.strptime(next_payment_str, "%Y-%m-%d")
                except ValueError:
                    self.app.notify("Invalid date format. Use YYYY-MM-DD")
                    return
            client = Client(
                id=client_id,
                name=name,
                company=self.query_one("#company", Input).value.strip(),
                email=self.query_one("#email", Input).value.strip(),
                phone=self.query_one("#phone", Input).value.strip(),
                billing_cycle=self.query_one("#billing-cycle", Input).value.strip()
                or "annual",
                amount=amount,
                currency=self.client.currency if self.client else "CAD",
                next_payment=self.query_one("#next-payment", Input).value.strip(),
                notes=self.query_one("#notes", Input).value.strip(),
                projects=self.client.projects if self.client else [],
            )
            self.dismiss(client)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        save_button = self.query_one("#save", Button)
        self.on_button_pressed(Button.Pressed(save_button))


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
