import re
import subprocess
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.widgets import Static, ListView, ListItem, Label
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual import events

from hawk.config import PROJECTS_PATH, ROUTINE_PATH, load_config
from hawk.db import Client, get_client_for_project
from hawk.utils import (
    get_git_branch,
    get_relative_time,
    parse_repo_path,
    launch_iterm_session,
)


class ProjectItem(ListItem):
    def __init__(
        self, name: str, status: str = "active", has_warning: bool = False
    ) -> None:
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
    def __init__(self) -> None:
        super().__init__()
        self.projects: list[str] = []

    def on_mount(self) -> None:
        self.load_projects()

    def on_key(self, event: events.Key) -> None:
        if event.key in ("right", "enter") and self.index is not None:
            detail_panel = self.app.query_one(DetailPanel)
            detail_panel.focus()
            event.stop()

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
                if (
                    not (project_dir / "session.md").exists()
                    or not (project_dir / "gotchas.md").exists()
                ):
                    has_warning = True
                self.projects.append(project_dir.name)
                self.append(ProjectItem(project_dir.name, status, has_warning))


class DetailPanel(Vertical):
    project_name = reactive("")

    def compose(self) -> ComposeResult:
        yield Static("Select a project", id="detail-header")
        yield Static("", id="detail-actions")
        yield Static("", id="detail-meta")
        yield Static("", id="detail-progress")
        yield Static("", id="detail-content")

    def on_mount(self) -> None:
        self._update_actions()

    def _update_actions(self, focused_idx: int = -1) -> None:
        labels = ["Editor", "OpenCode", "Claude"]
        parts = []
        for i, label in enumerate(labels):
            if i == focused_idx:
                parts.append(f"[black on #b8bb26] {label} [/]")
            else:
                parts.append(f"[#a89984]\\[{label}][/]")
        self.query_one("#detail-actions", Static).update("  ".join(parts))

    @property
    def action_labels(self) -> list[str]:
        return ["Editor", "OpenCode", "Claude"]

    focused_action: int = -1
    can_focus = True

    def on_focus(self) -> None:
        if self.focused_action < 0:
            self.focused_action = 0
        self._update_actions(self.focused_action)

    def on_blur(self) -> None:
        self._update_actions(-1)

    def on_key(self, event: events.Key) -> None:
        if event.key == "tab":
            return
        if event.key == "left":
            if self.focused_action <= 0:
                self.focused_action = -1
                self._update_actions(-1)
                self.app.query_one(ProjectList).focus()
            else:
                self.focused_action -= 1
                self._update_actions(self.focused_action)
            event.stop()
        elif event.key == "right":
            if self.focused_action < len(self.action_labels) - 1:
                self.focused_action += 1
                self._update_actions(self.focused_action)
            event.stop()
        elif event.key == "enter":
            self._execute_action(self.focused_action)
            event.stop()

    def _execute_action(self, idx: int) -> None:
        if not self.project_name or idx < 0:
            return
        project_path = PROJECTS_PATH / self.project_name
        project_md = project_path / "project.md"
        if not project_md.exists():
            self.app.notify("No project.md found")
            return
        repo_path = parse_repo_path(project_md.read_text())
        if not repo_path or not repo_path.exists():
            self.app.notify("Repo path missing or invalid")
            return

        config = load_config()
        if idx == 0:
            editor = config.get("tools", {}).get("editor", "antigravity")
            subprocess.Popen([editor, str(repo_path)])
            self.app.notify(f"Opening in {editor}")
        elif idx == 1:
            launch_iterm_session(repo_path, "opencode")
            self.app.notify(f"Launching opencode for {self.project_name}")
        elif idx == 2:
            launch_iterm_session(repo_path, "claude")
            self.app.notify(f"Launching claude for {self.project_name}")

    def watch_project_name(self, name: str) -> None:
        if not name:
            self.query_one("#detail-header", Static).update("Select a project")
            self.query_one("#detail-meta", Static).update("")
            self.query_one("#detail-progress", Static).update("")
            self.query_one("#detail-content", Static).update("")
            return

        self.query_one("#detail-header", Static).update(f"[bold]{name}[/bold]")
        project_path = PROJECTS_PATH / name
        content_parts: list[str] = []
        meta_parts: list[str] = []

        project_md = project_path / "project.md"
        repo_path = None
        if project_md.exists():
            project_content = project_md.read_text()
            repo_path = parse_repo_path(project_content)
            if repo_path:
                if repo_path.exists():
                    meta_parts.append(f"[dim]Repo: {repo_path}[/dim]")
                else:
                    meta_parts.append(f"[red]Repo: {repo_path} (not found)[/red]")
            else:
                meta_parts.append("[red]Repo: missing[/red]")
        else:
            meta_parts.append("[red]project.md missing[/red]")

        if repo_path and repo_path.exists():
            branch = get_git_branch(repo_path)
            if branch:
                meta_parts.append(f"[cyan]Branch:[/cyan] {branch}")

        linked_client = get_client_for_project(name)
        if linked_client:
            meta_parts.append(f"[magenta]Client:[/magenta] {linked_client.name}")

        session_md = project_path / "session.md"
        total_tasks = done_tasks = 0
        if session_md.exists():
            session_content = session_md.read_text()
            mtime = datetime.fromtimestamp(session_md.stat().st_mtime)
            meta_parts.append(
                f"[dim]{get_relative_time(mtime)} ({mtime.strftime('%b %d')})[/dim]"
            )
            done_tasks = len(re.findall(r"\[x\]", session_content, re.IGNORECASE))
            undone_tasks = len(re.findall(r"\[ \]", session_content))
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
            self.query_one("#detail-progress", Static).update(
                f"[green]{bar}[/green] {done_tasks}/{total_tasks} tasks"
            )
        else:
            self.query_one("#detail-progress", Static).update("")

        gotchas_md = project_path / "gotchas.md"
        if gotchas_md.exists():
            gotchas = []
            for line in gotchas_md.read_text().split("\n"):
                stripped = line.strip()
                if stripped.startswith(("-", "•")) and stripped not in ("---", "-"):
                    gotchas.append(line)
            if gotchas:
                content_parts.extend(
                    ["[yellow]## Gotchas[/yellow]", "\n".join(gotchas[:5])]
                )

        self.query_one("#detail-content", Static).update(
            "\n".join(content_parts) if content_parts else "No session.md found"
        )

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


class SOPPanel(Static):
    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]Session Routine[/bold cyan]", id="sop-title")
        yield Static("", id="sop-content")

    def on_mount(self) -> None:
        self._load_routine()

    def _load_routine(self) -> None:
        if ROUTINE_PATH.exists():
            content = ROUTINE_PATH.read_text()
            lines = []
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("## "):
                    lines.append(f"[green]{line[3:]}:[/green]")
                elif line.startswith('"'):
                    lines.append(f"  [dim]{line}[/dim]")
            self.query_one("#sop-content", Static).update("\n".join(lines))
        else:
            self.query_one("#sop-content", Static).update(
                "[dim]No routine.md found[/dim]"
            )


class AlertsPanel(Static):
    STALE_DAYS = 7

    def compose(self) -> ComposeResult:
        yield Static("No alerts", id="alerts-content")

    def check_alerts(self, projects: list[str]) -> list[tuple[str, list[str]]]:
        alerts: list[str] = []
        missing_files_map: list[tuple[str, list[str]]] = []
        for name in projects:
            project_alerts = self._check_project(name)
            for alert in project_alerts:
                if alert.startswith("missing"):
                    missing_files_map.append(
                        (name, alert.replace("missing ", "").split(", "))
                    )
                alerts.append(f"⚠ {name}: {alert}")
        self.query_one("#alerts-content", Static).update(
            "\n".join(alerts[:5]) if alerts else "✓ All projects healthy"
        )
        return missing_files_map

    def _check_project(self, name: str) -> list[str]:
        alerts: list[str] = []
        project_path = PROJECTS_PATH / name

        missing = []
        for f in ["project.md", "session.md", "gotchas.md"]:
            if not (project_path / f).exists():
                missing.append(f)
        if missing:
            alerts.append(f"missing {', '.join(missing)}")

        session_md = project_path / "session.md"
        if session_md.exists():
            mtime = datetime.fromtimestamp(session_md.stat().st_mtime)
            days_old = (datetime.now() - mtime).days
            if days_old > self.STALE_DAYS:
                alerts.append(f"session.md stale ({days_old}d)")

        project_md = project_path / "project.md"
        if project_md.exists():
            repo_path = parse_repo_path(project_md.read_text())
            if repo_path:
                if not repo_path.exists():
                    alerts.append("repo path not found")
                else:
                    claude_md = repo_path / "CLAUDE.md"
                    if not claude_md.exists():
                        alerts.append("CLAUDE.md missing in repo")
                    elif claude_md.is_symlink():
                        target = claude_md.resolve()
                        expected = project_path / "project.md"
                        if target != expected.resolve():
                            alerts.append("CLAUDE.md symlink incorrect")

                    agents_md = repo_path / "AGENTS.md"
                    if not agents_md.exists():
                        alerts.append("AGENTS.md missing in repo")
            else:
                alerts.append("no Repo: path in project.md")

        return alerts


class ClientItem(ListItem):
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


def get_all_clients():
    from hawk.db import get_all_clients as db_get_all_clients

    return db_get_all_clients()


class ClientDetailPanel(Static):
    client_id = reactive("")

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Select a client", id="client-header"),
            Static("", id="client-billing"),
            Static("", id="client-info"),
            Static("", id="client-projects"),
            id="client-inner",
        )

    def watch_client_id(self, client_id: str) -> None:
        from hawk.db import get_client

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

        billing_parts: list[str] = []
        status = client.payment_status()
        days = client.days_until_payment()
        if status == "overdue" and days is not None:
            billing_parts.append(f"[red bold]⚠ OVERDUE by {abs(days)} days[/red bold]")
        elif status == "due_soon" and days is not None:
            billing_parts.append(f"[yellow]Due in {days} days[/yellow]")
        elif client.next_payment:
            billing_parts.append(f"[green]✓ Paid[/green] (next: {client.next_payment})")

        if client.amount:
            billing_parts.append(
                f"[cyan]Amount:[/cyan] ${client.amount} {client.currency} ({client.billing_cycle})"
            )

        self.query_one("#client-billing", Static).update(
            "\n".join(billing_parts) if billing_parts else ""
        )

        info_parts: list[str] = []
        if client.company:
            info_parts.append(f"[cyan]Company:[/cyan] {client.company}")
        if client.email:
            info_parts.append(f"[cyan]Email:[/cyan] {client.email}")
        if client.phone:
            info_parts.append(f"[cyan]Phone:[/cyan] {client.phone}")
        if client.notes:
            info_parts.append(f"[dim]{client.notes}[/dim]")

        self.query_one("#client-info", Static).update(
            "\n".join(info_parts) if info_parts else ""
        )

        if client.projects:
            self.query_one("#client-projects", Static).update(
                f"\n[green]Projects:[/green]\n"
                + "\n".join(f"  • {p}" for p in client.projects)
            )
        else:
            self.query_one("#client-projects", Static).update(
                "\n[dim]No linked projects[/dim]"
            )
