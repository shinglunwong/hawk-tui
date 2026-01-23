from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static, ListView
from textual.containers import Vertical

from hawk.config import PROJECTS_PATH
from hawk.db import Client, get_client, delete_client, CLIENTS_PATH
from hawk.screens import DeleteClientScreen, HealthCheckScreen
from hawk.widgets import (
    ProjectList,
    DetailPanel,
    SOPPanel,
    AlertsPanel,
    ClientList,
    ClientDetailPanel,
    ProjectItem,
    ClientItem,
)

CSS = """
$bg: #282828;
$bg1: #3c3836;
$bg2: #504945;
$fg: #ebdbb2;
$fg-dim: #a89984;
$red: #fb4934;
$green: #b8bb26;
$yellow: #fabd2f;
$blue: #83a598;
$purple: #d3869b;
$aqua: #8ec07c;
$orange: #fe8019;

Screen {
    layout: grid;
    grid-size: 2 3;
    grid-columns: 30 1fr;
    grid-rows: auto 1fr auto;
    background: $bg;
}

#view-indicator {
    column-span: 2;
    height: 1;
    background: $bg1;
    color: $orange;
    padding: 0 1;
}

#left-panel, #left-panel-clients {
    layout: vertical;
    height: 100%;
}

ProjectList, ClientList {
    border: solid $green;
    padding: 0 1;
    height: 1fr;
    background: $bg;
}

ProjectList > ListItem, ClientList > ListItem {
    padding: 0 1;
    color: $fg;
}

ProjectList > ListItem.--highlight, ClientList > ListItem.--highlight {
    background: $bg2;
    color: $yellow;
}

#sop-panel {
    border: solid $aqua;
    padding: 0 1;
    height: auto;
    max-height: 10;
    background: $bg;
}

#sop-title {
    text-style: bold;
    color: $aqua;
}

#details, #client-details {
    border: solid $green;
    padding: 1;
    background: $bg;
    color: $fg;
}

#detail-header, #client-header {
    text-style: bold;
    color: $yellow;
}

#detail-meta {
    padding-bottom: 1;
    color: $fg-dim;
}

#detail-progress {
    padding-bottom: 1;
}

#detail-actions {
    height: 1;
    color: $fg-dim;
}

#alerts {
    column-span: 2;
    height: auto;
    max-height: 5;
    border: solid $yellow;
    padding: 0 1;
    background: $bg1;
    color: $fg;
}

Header {
    background: $bg1;
    color: $fg;
}

Footer {
    column-span: 2;
    background: $bg1;
}

Footer > .footer--key {
    color: $orange;
    background: $bg2;
}

Footer > .footer--description {
    color: $fg;
}

#empty-state {
    column-span: 2;
    row-span: 1;
    align: center middle;
    color: $fg;
}

.hidden {
    display: none;
}
"""


class HawkApp(App):
    TITLE = "hawk-tui"
    CSS = CSS

    BINDINGS = [
        Binding("q", "quit_app", "Quit"),
        Binding("tab", "switch_view", "Switch", priority=True),
        Binding("c", "show_health_check", "Check"),
        Binding("n", "new_client", "New"),
        Binding("d", "delete_client", "Delete"),
    ]

    current_project: str = ""
    current_client_id: str = ""
    current_view: str = "projects"
    missing_files_map: list = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[bold]Projects[/bold] | Clients", id="view-indicator")

        if not PROJECTS_PATH.exists() or not any(PROJECTS_PATH.iterdir()):
            yield Static(
                "[bold]Welcome to hawk-tui![/bold]\n\n"
                "No projects found in ~/ai/projects/\n\n"
                "Create a project folder to get started:\n"
                "  mkdir -p ~/ai/projects/my-project\n\n"
                "Then add project.md, session.md, gotchas.md",
                id="empty-state",
            )
        else:
            with Vertical(id="left-panel"):
                yield ProjectList()
                yield SOPPanel(id="sop-panel")
            yield DetailPanel(id="details")

        with Vertical(id="left-panel-clients", classes="hidden"):
            yield ClientList()
        yield ClientDetailPanel(id="client-details", classes="hidden")

        yield AlertsPanel(id="alerts")
        yield Footer()

    def on_mount(self) -> None:
        try:
            project_list = self.query_one(ProjectList)
            project_list.focus()
            if project_list.projects:
                self.current_project = project_list.projects[0]
                self.query_one(DetailPanel).project_name = self.current_project
            self.set_timer(0.1, self._check_alerts)
        except Exception:
            pass

    def _check_alerts(self) -> None:
        try:
            self.missing_files_map = self.query_one(AlertsPanel).check_alerts(
                self.query_one(ProjectList).projects
            )
        except Exception:
            pass

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, ProjectItem):
            self.current_project = event.item.project_name
            self.query_one(DetailPanel).project_name = event.item.project_name
        elif isinstance(event.item, ClientItem):
            self.current_client_id = event.item.client.id
            self.query_one(ClientDetailPanel).client_id = event.item.client.id

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ClientItem):
            self._edit_client()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        clients_actions = {"new_client", "delete_client"}
        if self.current_view == "projects" and action in clients_actions:
            return False
        return True

    def action_switch_view(self) -> None:
        try:
            left_projects = self.query_one("#left-panel", Vertical)
            detail_panel = self.query_one(DetailPanel)
            left_clients = self.query_one("#left-panel-clients", Vertical)
            client_detail = self.query_one(ClientDetailPanel)
            indicator = self.query_one("#view-indicator", Static)

            if self.current_view == "projects":
                self.current_view = "clients"
                left_projects.add_class("hidden")
                detail_panel.add_class("hidden")
                left_clients.remove_class("hidden")
                client_detail.remove_class("hidden")
                self.query_one(ClientList).focus()
                indicator.update("[bold]Clients[/bold] | Projects")
                client_list = self.query_one(ClientList)
                if client_list.clients:
                    self.current_client_id = client_list.clients[0].id
                    self.query_one(ClientDetailPanel).client_id = self.current_client_id
            else:
                self.current_view = "projects"
                left_clients.add_class("hidden")
                client_detail.add_class("hidden")
                left_projects.remove_class("hidden")
                detail_panel.remove_class("hidden")
                self.query_one(ProjectList).focus()
                indicator.update("[bold]Projects[/bold] | Clients")
            self.refresh_bindings()
        except Exception:
            pass

    def action_show_health_check(self) -> None:
        self.push_screen(HealthCheckScreen())

    def action_quit_app(self) -> None:
        self.exit()

    def action_new_client(self) -> None:
        import subprocess
        from hawk.config import load_config

        config = load_config()
        editor = config.get("tools", {}).get("editor", "code")
        subprocess.Popen([editor, str(CLIENTS_PATH)])
        self.notify(f"Opening {CLIENTS_PATH.name} in {editor}")

    def _edit_client(self) -> None:
        import subprocess
        from hawk.config import load_config

        config = load_config()
        editor = config.get("tools", {}).get("editor", "code")
        subprocess.Popen([editor, str(CLIENTS_PATH)])
        self.notify(f"Opening {CLIENTS_PATH.name} in {editor}")

    def action_delete_client(self) -> None:
        if self.current_view != "clients" or not self.current_client_id:
            return
        client = get_client(self.current_client_id)
        if not client:
            return

        def handle_delete(confirmed: bool | None) -> None:
            if confirmed:
                delete_client(self.current_client_id)
                self.current_client_id = ""
                self.query_one(ClientList).load_clients()
                self.query_one(ClientDetailPanel).client_id = ""
                self.notify(f"Deleted client: {client.name}")

        self.push_screen(DeleteClientScreen(client.name), handle_delete)


def main():
    app = HawkApp()
    app.run()


if __name__ == "__main__":
    main()
