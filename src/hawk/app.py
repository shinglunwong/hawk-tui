"""Main hawk-tui application."""

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Header, Static, ListView, ListItem, Label, Button, Input
from textual.containers import Vertical, Horizontal, Center, Grid
from textual.reactive import reactive

from hawk.db import (
    Client, get_all_clients, get_client, create_client, update_client, delete_client,
    get_client_for_project, link_project_to_client, get_projects_for_client,
    unlink_project_from_client, get_upcoming_payments
)


# Paths
PROJECTS_PATH = Path.home() / "ai" / "projects"
CONFIG_PATH = Path.home() / "ai" / "projects" / "hawk-tui" / "data" / "config.toml"


def load_config() -> dict:
    """Load config from config.toml."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    return {
        "tools": {"ai_tools": ["claude", "opencode"], "default_ai_tool": "", "editor": "antigravity", "terminal": "iterm"},
        "paths": {"projects": "~/ai/projects"}
    }


CONFIG = load_config()


def get_git_branch(repo_path: Path) -> str:
    """Get current git branch for a repo."""
    if not repo_path.exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=2
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def get_relative_time(dt: datetime) -> str:
    """Convert datetime to relative time string."""
    now = datetime.now()
    diff = now - dt
    if diff.days > 30:
        return f"{diff.days // 30} months ago"
    elif diff.days > 0:
        return f"{diff.days} days ago" if diff.days > 1 else "yesterday"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hours ago" if hours > 1 else "1 hour ago"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60} min ago"
    else:
        return "just now"


def parse_repo_path(content: str) -> Path | None:
    """Extract repo path from project.md content."""
    for line in content.split("\n"):
        if line.startswith("Repo:"):
            path_str = line.replace("Repo:", "").strip()
            if path_str.startswith("~"):
                path_str = str(Path.home()) + path_str[1:]
            return Path(path_str)
    return None


def launch_iterm_session(repo_path: Path, tool: str) -> None:
    """Launch iTerm with AI tool in the repo directory."""
    # Escape path for shell
    path_str = str(repo_path).replace('"', '\\"')
    script = f'''
    tell application "iTerm"
        activate
        if (count of windows) = 0 then
            create window with default profile
        else
            tell current window
                create tab with default profile
            end tell
        end if
        tell current session of current window
            write text "cd \\"{path_str}\\" && {tool}"
            delay 1
            write text "read session context"
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script])


# --- Screens ---

class HelpScreen(ModalScreen):
    """Help screen with shortcuts and tips."""

    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("f1", "dismiss", "Close")]

    CSS = """
    HelpScreen { align: center middle; }
    #help-dialog {
        width: 60;
        height: 26;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #help-title { text-align: center; text-style: bold; padding-bottom: 1; }
    .section { padding-top: 1; color: $text; }
    .section-title { text-style: bold; color: $accent; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static("hawk-tui Help", id="help-title")
            yield Static("[bold cyan]Navigation[/bold cyan]", classes="section-title")
            yield Static("Tab       Switch Projects/Clients\n↑↓        Navigate list", classes="section")
            yield Static("[bold cyan]Projects View[/bold cyan]", classes="section-title")
            yield Static("a         Start AI session\ne         Open in editor\nl         Link to client\nc         Check integrity\ns         Sync projects", classes="section")
            yield Static("[bold cyan]Clients View[/bold cyan]", classes="section-title")
            yield Static("n         New client\nEnter     Edit client\nd         Delete client", classes="section")
            yield Static("[bold cyan]General[/bold cyan]", classes="section-title")
            yield Static("F1        This help\nq         Quit", classes="section")

    def action_dismiss(self) -> None:
        self.app.pop_screen()


class ToolSelectScreen(ModalScreen[str]):
    """Modal to select AI tool."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    ToolSelectScreen { align: center middle; }
    #tool-dialog { width: 40; height: 12; border: thick $accent; background: $surface; padding: 1 2; }
    #tool-title { text-align: center; text-style: bold; padding-bottom: 1; }
    Button { width: 100%; margin: 1 0; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="tool-dialog"):
            yield Static("Select AI Tool", id="tool-title")
            yield Button("Claude Code", id="claude", variant="primary")
            yield Button("OpenCode", id="opencode")
            yield Button("Cancel", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "claude":
            self.dismiss("claude")
        elif event.button.id == "opencode":
            self.dismiss("opencode")
        else:
            self.dismiss("")

    def action_cancel(self) -> None:
        self.dismiss("")


class QuitScreen(ModalScreen[bool]):
    """Quit confirmation screen."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    QuitScreen { align: center middle; }
    #quit-dialog { width: 40; height: 8; border: thick $accent; background: $surface; padding: 1 2; }
    #quit-title { text-align: center; text-style: bold; padding-bottom: 1; }
    Horizontal { align: center middle; }
    Button { margin: 0 1; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="quit-dialog"):
            yield Static("Quit hawk-tui?", id="quit-title")
            with Horizontal():
                yield Button("Quit", id="yes", variant="error")
                yield Button("Cancel", id="no", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class CreateFileScreen(ModalScreen[bool]):
    """Offer to create missing files."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    CreateFileScreen { align: center middle; }
    #create-dialog { width: 50; height: 10; border: thick $accent; background: $surface; padding: 1 2; }
    #create-title { text-align: center; text-style: bold; padding-bottom: 1; }
    Horizontal { align: center middle; padding-top: 1; }
    Button { margin: 0 1; }
    """

    def __init__(self, project: str, missing_files: list[str]) -> None:
        super().__init__()
        self.project = project
        self.missing_files = missing_files

    def compose(self) -> ComposeResult:
        with Vertical(id="create-dialog"):
            yield Static(f"Missing files in {self.project}", id="create-title")
            yield Static(f"Missing: {', '.join(self.missing_files)}")
            yield Static("Create from template?")
            with Horizontal():
                yield Button("Create", id="yes", variant="primary")
                yield Button("Skip", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class RepoPathScreen(ModalScreen[str]):
    """Prompt for repo path."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

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

    def compose(self) -> ComposeResult:
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


class ClientFormScreen(ModalScreen[Optional[Client]]):
    """Add or edit a client."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

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

    def compose(self) -> ComposeResult:
        title = "Edit Client" if self.client else "Add Client"
        with Vertical(id="client-dialog"):
            yield Static(title, id="client-title")
            # Basic info
            with Horizontal(classes="field-row"):
                yield Static("ID (slug):", classes="field-label")
                yield Input(value=self.client.id if self.client else "", id="client-id", classes="field-input", disabled=bool(self.client))
            with Horizontal(classes="field-row"):
                yield Static("Name:", classes="field-label")
                yield Input(value=self.client.name if self.client else "", id="name", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Static("Company:", classes="field-label")
                yield Input(value=self.client.company if self.client else "", id="company", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Static("Email:", classes="field-label")
                yield Input(value=self.client.email if self.client else "", id="email", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Static("Phone:", classes="field-label")
                yield Input(value=self.client.phone if self.client else "", id="phone", classes="field-input")
            # Billing
            yield Static("Billing", classes="section-title")
            with Horizontal(classes="field-row"):
                yield Static("Cycle:", classes="field-label")
                yield Input(value=self.client.billing_cycle if self.client else "annual", id="billing-cycle", classes="field-input", placeholder="annual / monthly / one-time")
            with Horizontal(classes="field-row"):
                yield Static("Amount:", classes="field-label")
                yield Input(value=str(self.client.amount) if self.client else "0", id="amount", classes="field-input")
            with Horizontal(classes="field-row"):
                yield Static("Next Payment:", classes="field-label")
                yield Input(value=self.client.next_payment if self.client else "", id="next-payment", classes="field-input", placeholder="YYYY-MM-DD")
            with Horizontal(classes="field-row"):
                yield Static("Notes:", classes="field-label")
                yield Input(value=self.client.notes if self.client else "", id="notes", classes="field-input")
            with Horizontal(id="button-row"):
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
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
            client = Client(
                id=client_id,
                name=name,
                company=self.query_one("#company", Input).value.strip(),
                email=self.query_one("#email", Input).value.strip(),
                phone=self.query_one("#phone", Input).value.strip(),
                billing_cycle=self.query_one("#billing-cycle", Input).value.strip() or "annual",
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


class DeleteClientScreen(ModalScreen[bool]):
    """Confirm client deletion."""

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

    def compose(self) -> ComposeResult:
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
    """Link a project to a client."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    LinkClientScreen { align: center middle; }
    #link-dialog { width: 50; height: 16; border: thick $accent; background: $surface; padding: 1 2; }
    #link-title { text-align: center; text-style: bold; padding-bottom: 1; }
    ListView { height: 8; border: solid $primary; }
    Horizontal { align: center middle; padding-top: 1; }
    Button { margin: 0 1; }
    """

    def __init__(self, project_name: str, current_client_id: Optional[str] = None) -> None:
        super().__init__()
        self.project_name = project_name
        self.current_client_id = current_client_id
        self.clients = get_all_clients()
        self.selected_id: Optional[str] = current_client_id

    def compose(self) -> ComposeResult:
        with Vertical(id="link-dialog"):
            yield Static(f"Link {self.project_name} to client", id="link-title")
            lv = ListView()
            lv.append(ListItem(Label("(No client)"), id="client-none"))
            for c in self.clients:
                lv.append(ListItem(Label(f"{c.name} ({c.company})" if c.company else c.name), id=f"client-{c.id}"))
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
            self.dismiss(self.current_client_id)  # No change

    def action_cancel(self) -> None:
        self.dismiss(self.current_client_id)  # No change


# --- Widgets ---

class ProjectItem(ListItem):
    """A single project in the list."""

    def __init__(self, name: str, status: str = "active", has_warning: bool = False) -> None:
        super().__init__()
        self.project_name = name
        self.project_status = status
        self.has_warning = has_warning

    def compose(self) -> ComposeResult:
        icon = "●" if self.project_status == "active" else "○"
        warning = " ⚠" if self.has_warning else ""
        if self.project_status == "active":
            yield Label(f"{icon} {self.project_name}{warning}")
        else:
            yield Label(f"[dim]{icon} {self.project_name}{warning}[/dim]")


class ProjectList(ListView):
    """Left panel: selectable list of projects."""

    def __init__(self) -> None:
        super().__init__()
        self.projects = []

    def on_mount(self) -> None:
        self.load_projects()

    def load_projects(self) -> None:
        self.clear()
        self.projects = []
        if not PROJECTS_PATH.exists():
            return
        for project_dir in sorted(PROJECTS_PATH.iterdir()):
            if project_dir.is_dir() and not project_dir.name.startswith("."):
                status = "active"
                has_warning = False
                project_md = project_dir / "project.md"
                if project_md.exists():
                    content = project_md.read_text()
                    if "Status: archived" in content:
                        status = "archived"
                # Check for warnings
                if not (project_dir / "session.md").exists() or not (project_dir / "gotchas.md").exists():
                    has_warning = True
                self.projects.append(project_dir.name)
                self.append(ProjectItem(project_dir.name, status, has_warning))


class DetailPanel(Static):
    """Right panel: project details."""

    project_name = reactive("")

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Select a project", id="detail-header"),
            Static("", id="detail-meta"),
            Static("", id="detail-progress"),
            Static("", id="detail-content"),
            id="detail-inner"
        )

    def watch_project_name(self, name: str) -> None:
        if not name:
            self.query_one("#detail-header", Static).update("Select a project")
            self.query_one("#detail-meta", Static).update("")
            self.query_one("#detail-progress", Static).update("")
            self.query_one("#detail-content", Static).update("")
            return

        self.query_one("#detail-header", Static).update(f"[bold]{name}[/bold]")
        project_path = PROJECTS_PATH / name
        content_parts = []
        meta_parts = []

        # Read project.md for repo path
        project_md = project_path / "project.md"
        repo_path = None
        if project_md.exists():
            project_content = project_md.read_text()
            repo_path = parse_repo_path(project_content)
            if repo_path:
                meta_parts.append(f"[dim]Repo: {repo_path}[/dim]")

        # Get git branch
        if repo_path and repo_path.exists():
            branch = get_git_branch(repo_path)
            if branch:
                meta_parts.append(f"[cyan]Branch:[/cyan] {branch}")

        # Read session.md
        session_md = project_path / "session.md"
        total_tasks = done_tasks = 0
        if session_md.exists():
            session_content = session_md.read_text()
            mtime = datetime.fromtimestamp(session_md.stat().st_mtime)
            meta_parts.append(f"[dim]{get_relative_time(mtime)} ({mtime.strftime('%b %d')})[/dim]")
            done_tasks = len(re.findall(r'\[x\]', session_content, re.IGNORECASE))
            undone_tasks = len(re.findall(r'\[ \]', session_content))
            total_tasks = done_tasks + undone_tasks
            whats_next = self._extract_section(session_content, "## What's Next")
            if whats_next:
                content_parts.extend(["[green]## What's Next[/green]", whats_next, ""])
            recent_work = self._extract_section(session_content, "## Recent Work")
            if recent_work:
                content_parts.extend(["[blue]## Recent Work[/blue]", recent_work, ""])

        self.query_one("#detail-meta", Static).update("\n".join(meta_parts))

        if total_tasks > 0:
            filled = int(20 * done_tasks / total_tasks)
            bar = "█" * filled + "░" * (20 - filled)
            self.query_one("#detail-progress", Static).update(f"[green]{bar}[/green] {done_tasks}/{total_tasks} tasks")
        else:
            self.query_one("#detail-progress", Static).update("")

        # Read gotchas.md
        gotchas_md = project_path / "gotchas.md"
        if gotchas_md.exists():
            gotchas = [l for l in gotchas_md.read_text().split("\n") if l.strip().startswith(("-", "•"))]
            if gotchas:
                content_parts.extend(["[yellow]## Gotchas[/yellow]", "\n".join(gotchas[:5])])

        self.query_one("#detail-content", Static).update("\n".join(content_parts) if content_parts else "No session.md found")

    def _extract_section(self, content: str, header: str) -> str:
        lines, in_section, section_lines = content.split("\n"), False, []
        for line in lines:
            if line.startswith(header):
                in_section = True
            elif in_section and line.startswith("## "):
                break
            elif in_section and line.strip():
                section_lines.append(line)
        return "\n".join(section_lines[:10])


class AlertsPanel(Static):
    """Bottom panel: alerts and warnings."""

    def compose(self) -> ComposeResult:
        yield Static("No alerts", id="alerts-content")

    def check_alerts(self, projects: list[str]) -> list[tuple[str, list[str]]]:
        alerts = []
        missing_files_map = []
        for name in projects:
            project_path = PROJECTS_PATH / name
            missing = []
            if not (project_path / "session.md").exists():
                missing.append("session.md")
            if not (project_path / "gotchas.md").exists():
                missing.append("gotchas.md")
            if missing:
                alerts.append(f"⚠ {name}: missing {', '.join(missing)}")
                missing_files_map.append((name, missing))
            project_md = project_path / "project.md"
            if project_md.exists():
                repo_path = parse_repo_path(project_md.read_text())
                if repo_path and not repo_path.exists():
                    alerts.append(f"⚠ {name}: repo path not found")
        self.query_one("#alerts-content", Static).update("\n".join(alerts[:3]) if alerts else "✓ No alerts")
        return missing_files_map


class ClientItem(ListItem):
    """A single client in the list."""

    def __init__(self, client: Client) -> None:
        super().__init__()
        self.client = client

    def compose(self) -> ComposeResult:
        status = self.client.payment_status()
        if status == "overdue":
            icon = "[red]✗[/red]"
        elif status == "due_soon":
            icon = "[yellow]⚠[/yellow]"
        else:
            icon = "[green]✓[/green]"
        display = f"{icon} {self.client.name}"
        if self.client.company:
            display += f" [dim]({self.client.company})[/dim]"
        yield Label(display)


class ClientList(ListView):
    """Left panel: selectable list of clients."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.clients: list[Client] = []

    def on_mount(self) -> None:
        self.load_clients()

    def load_clients(self) -> None:
        self.clear()
        self.clients = get_all_clients()
        for client in self.clients:
            self.append(ClientItem(client))


class ClientDetailPanel(Static):
    """Right panel: client details."""

    client_id = reactive("")

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Select a client", id="client-header"),
            Static("", id="client-billing"),
            Static("", id="client-info"),
            Static("", id="client-projects"),
            id="client-inner"
        )

    def watch_client_id(self, client_id: str) -> None:
        if not client_id:
            self.query_one("#client-header", Static).update("Select a client")
            self.query_one("#client-billing", Static).update("")
            self.query_one("#client-info", Static).update("")
            self.query_one("#client-projects", Static).update("")
            return

        client = get_client(client_id)
        if not client:
            return

        self.query_one("#client-header", Static).update(f"[bold]{client.name}[/bold]")

        # Billing info
        billing_parts = []
        status = client.payment_status()
        days = client.days_until_payment()
        if status == "overdue":
            billing_parts.append(f"[red bold]⚠ OVERDUE by {abs(days)} days[/red bold]")
        elif status == "due_soon":
            billing_parts.append(f"[yellow]Due in {days} days[/yellow]")
        elif client.next_payment:
            billing_parts.append(f"[green]✓ Paid[/green] (next: {client.next_payment})")

        if client.amount:
            billing_parts.append(f"[cyan]Amount:[/cyan] ${client.amount} {client.currency} ({client.billing_cycle})")

        self.query_one("#client-billing", Static).update("\n".join(billing_parts) if billing_parts else "")

        # Contact info
        info_parts = []
        if client.company:
            info_parts.append(f"[cyan]Company:[/cyan] {client.company}")
        if client.email:
            info_parts.append(f"[cyan]Email:[/cyan] {client.email}")
        if client.phone:
            info_parts.append(f"[cyan]Phone:[/cyan] {client.phone}")
        if client.notes:
            info_parts.append(f"[dim]{client.notes}[/dim]")

        self.query_one("#client-info", Static).update("\n".join(info_parts) if info_parts else "")

        # Show linked projects
        if client.projects:
            self.query_one("#client-projects", Static).update(f"\n[green]Projects:[/green]\n" + "\n".join(f"  • {p}" for p in client.projects))
        else:
            self.query_one("#client-projects", Static).update("\n[dim]No linked projects[/dim]")


# --- Main App ---

class HawkApp(App):
    """Main hawk-tui application."""

    TITLE = "hawk-tui"
    CSS = """
    Screen { layout: grid; grid-size: 2 2; grid-rows: 1fr auto; }
    ProjectList, ClientList { width: 25; border: solid green; padding: 0 1; }
    ProjectList > ListItem, ClientList > ListItem { padding: 0 1; }
    ProjectList > ListItem.--highlight, ClientList > ListItem.--highlight { background: $accent; }
    #details, #client-details { border: solid green; padding: 1; }
    #detail-header, #client-header { text-style: bold; }
    #detail-meta { padding-bottom: 1; }
    #detail-progress { padding-bottom: 1; }
    #alerts { column-span: 2; height: auto; max-height: 5; border: solid yellow; padding: 0 1; }
    Footer { column-span: 2; }
    #empty-state { column-span: 2; row-span: 2; align: center middle; }
    #view-indicator { column-span: 2; height: 1; background: $primary; color: $text; padding: 0 1; }
    .hidden { display: none; }
    """

    BINDINGS = [
        Binding("q", "quit_app", "Quit"),
        Binding("f1", "help", "Help"),
        Binding("tab", "switch_view", "Switch View"),
        Binding("c", "check", "Check"),
        Binding("s", "sync", "Sync"),
        Binding("e", "open_editor", "Editor"),
        Binding("a", "select_project", "AI Session"),
        Binding("n", "new_client", "New Client"),
        Binding("enter", "edit_client", "Edit", show=False),
        Binding("d", "delete_client", "Delete", show=False),
        Binding("l", "link_client", "Link Client"),
    ]

    current_project: str = ""
    current_client_id: str = ""
    current_view: str = "projects"  # "projects" or "clients"
    missing_files_map: list = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[Tab] Projects | Clients", id="view-indicator")

        # Projects view
        project_list = ProjectList()
        if not PROJECTS_PATH.exists() or not any(PROJECTS_PATH.iterdir()):
            yield Static("[bold]Welcome to hawk-tui![/bold]\n\nNo projects found in ~/ai/projects/\n\nCreate a project folder to get started:\n  mkdir -p ~/ai/projects/my-project\n\nThen add project.md, session.md, gotchas.md", id="empty-state")
        else:
            yield project_list
            yield DetailPanel(id="details")

        # Clients view (hidden by default)
        yield ClientList(classes="hidden")
        yield ClientDetailPanel(id="client-details", classes="hidden")

        yield AlertsPanel(id="alerts")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.query_one(ProjectList).focus()
            self.set_timer(0.1, self._check_alerts)
        except Exception:
            pass

    def _check_alerts(self) -> None:
        try:
            self.missing_files_map = self.query_one(AlertsPanel).check_alerts(self.query_one(ProjectList).projects)
        except Exception:
            pass

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, ProjectItem):
            self.current_project = event.item.project_name
            self.query_one(DetailPanel).project_name = event.item.project_name
        elif isinstance(event.item, ClientItem):
            self.current_client_id = event.item.client.id
            self.query_one(ClientDetailPanel).client_id = event.item.client.id

    def action_switch_view(self) -> None:
        """Switch between Projects and Clients view."""
        try:
            project_list = self.query_one(ProjectList)
            detail_panel = self.query_one(DetailPanel)
            client_list = self.query_one(ClientList)
            client_detail = self.query_one(ClientDetailPanel)
            indicator = self.query_one("#view-indicator", Static)

            if self.current_view == "projects":
                # Switch to clients
                self.current_view = "clients"
                project_list.add_class("hidden")
                detail_panel.add_class("hidden")
                client_list.remove_class("hidden")
                client_detail.remove_class("hidden")
                client_list.focus()
                indicator.update("[Tab] Projects | [bold]Clients[/bold]")
            else:
                # Switch to projects
                self.current_view = "projects"
                client_list.add_class("hidden")
                client_detail.add_class("hidden")
                project_list.remove_class("hidden")
                detail_panel.remove_class("hidden")
                project_list.focus()
                indicator.update("[Tab] [bold]Projects[/bold] | Clients")
        except Exception:
            pass

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_quit_app(self) -> None:
        def handle_quit(confirmed: bool) -> None:
            if confirmed:
                self.exit()
        self.push_screen(QuitScreen(), handle_quit)

    def action_check(self) -> None:
        self._check_alerts()
        # Offer to create missing files
        if self.missing_files_map:
            project, missing = self.missing_files_map[0]
            def handle_create(create: bool) -> None:
                if create:
                    self._create_missing_files(project, missing)
                    self._check_alerts()
                    self.query_one(ProjectList).load_projects()
            self.push_screen(CreateFileScreen(project, missing), handle_create)
        else:
            self.notify("✓ All files present")

    def _create_missing_files(self, project: str, missing: list[str]) -> None:
        project_path = PROJECTS_PATH / project
        if "session.md" in missing:
            (project_path / "session.md").write_text(f"# {project} - Session\n\n## Current Focus\n\n## What's Next\n- [ ] Task 1\n\n## Recent Work\n- [x] Initial setup\n")
        if "gotchas.md" in missing:
            (project_path / "gotchas.md").write_text("# Gotchas & Traps\n\n---\n\n<!-- Add gotchas as discovered -->\n")
        self.notify(f"Created missing files for {project}")

    def action_sync(self) -> None:
        self.query_one(ProjectList).load_projects()
        self._check_alerts()
        self.notify(f"Synced {len(self.query_one(ProjectList).projects)} projects")

    def action_select_project(self) -> None:
        if not self.current_project:
            self.notify("No project selected")
            return
        project_path = PROJECTS_PATH / self.current_project
        project_md = project_path / "project.md"
        if not project_md.exists():
            self.notify("No project.md found")
            return
        repo_path = parse_repo_path(project_md.read_text())
        if not repo_path:
            def handle_repo_path(path: str) -> None:
                if path:
                    # Save to project.md
                    content = project_md.read_text()
                    with open(project_md, "w") as f:
                        f.write(content.rstrip() + f"\n\nRepo: {path}\n")
                    self.notify(f"Saved repo path: {path}")
            self.push_screen(RepoPathScreen(self.current_project), handle_repo_path)
            return
        if not repo_path.exists():
            self.notify(f"Repo path not found: {repo_path}")
            return
        def handle_tool(tool: str) -> None:
            if tool:
                launch_iterm_session(repo_path, tool)
                self.notify(f"Launching {tool} for {self.current_project}")
        self.push_screen(ToolSelectScreen(), handle_tool)

    def action_open_editor(self) -> None:
        if not self.current_project:
            self.notify("No project selected")
            return
        project_md = PROJECTS_PATH / self.current_project / "project.md"
        if not project_md.exists():
            self.notify("No project.md found")
            return
        repo_path = parse_repo_path(project_md.read_text())
        if repo_path and repo_path.exists():
            editor = CONFIG.get("tools", {}).get("editor", "antigravity")
            subprocess.Popen([editor, str(repo_path)])
            self.notify(f"Opening in {editor}")
        else:
            self.notify("No valid repo path")

    def action_new_client(self) -> None:
        """Add a new client."""
        def handle_client(client: Optional[Client]) -> None:
            if client:
                create_client(client)
                self.query_one(ClientList).load_clients()
                self.notify(f"Created client: {client.name}")
        self.push_screen(ClientFormScreen(), handle_client)

    def action_edit_client(self) -> None:
        """Edit the selected client."""
        if self.current_view != "clients" or not self.current_client_id:
            return
        client = get_client(self.current_client_id)
        if not client:
            return
        def handle_client(updated: Optional[Client]) -> None:
            if updated:
                update_client(updated)
                self.query_one(ClientList).load_clients()
                self.query_one(ClientDetailPanel).client_id = updated.id
                self.notify(f"Updated client: {updated.name}")
        self.push_screen(ClientFormScreen(client), handle_client)

    def action_delete_client(self) -> None:
        """Delete the selected client."""
        if self.current_view != "clients" or not self.current_client_id:
            return
        client = get_client(self.current_client_id)
        if not client:
            return
        def handle_delete(confirmed: bool) -> None:
            if confirmed:
                delete_client(self.current_client_id)
                self.current_client_id = ""
                self.query_one(ClientList).load_clients()
                self.query_one(ClientDetailPanel).client_id = ""
                self.notify(f"Deleted client: {client.name}")
        self.push_screen(DeleteClientScreen(client.name), handle_delete)

    def action_link_client(self) -> None:
        """Link current project to a client."""
        if self.current_view != "projects" or not self.current_project:
            self.notify("Select a project first")
            return
        current_client = get_client_for_project(self.current_project)
        current_id = current_client.id if current_client else None
        def handle_link(client_id: Optional[str]) -> None:
            if client_id is None and current_id is not None:
                unlink_project_from_client(self.current_project)
                self.notify(f"Unlinked {self.current_project}")
            elif client_id is not None:
                link_project_to_client(self.current_project, client_id)
                client = get_client(client_id)
                self.notify(f"Linked to {client.name}")
        self.push_screen(LinkClientScreen(self.current_project, current_id), handle_link)


def main():
    app = HawkApp()
    app.run()


if __name__ == "__main__":
    main()
