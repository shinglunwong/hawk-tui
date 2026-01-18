"""Main hawk-tui application."""

import re
import subprocess
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Static, ListView, ListItem, Label, Button
from textual.containers import Vertical, Horizontal, Center
from textual.reactive import reactive


# Path to projects
PROJECTS_PATH = Path.home() / "ai" / "projects"


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
        mins = diff.seconds // 60
        return f"{mins} min ago"
    else:
        return "just now"


def parse_repo_path(content: str) -> Path | None:
    """Extract repo path from project.md content."""
    for line in content.split("\n"):
        if line.startswith("Repo:"):
            path_str = line.replace("Repo:", "").strip()
            # Expand ~ to home directory
            if path_str.startswith("~"):
                path_str = str(Path.home()) + path_str[1:]
            return Path(path_str)
    return None


def launch_iterm_session(repo_path: Path, tool: str) -> None:
    """Launch iTerm with AI tool in the repo directory."""
    # AppleScript to open new iTerm tab, cd, and run tool
    script = f'''
    tell application "iTerm"
        activate
        tell current window
            create tab with default profile
            tell current session
                write text "cd {repo_path} && {tool}"
                delay 1
                write text "read session context"
            end tell
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script], capture_output=True)


class ToolSelectScreen(ModalScreen[str]):
    """Modal to select AI tool."""

    CSS = """
    ToolSelectScreen {
        align: center middle;
    }
    #tool-dialog {
        width: 40;
        height: 12;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #tool-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    Button {
        width: 100%;
        margin: 1 0;
    }
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


class ProjectItem(ListItem):
    """A single project in the list."""

    def __init__(self, name: str, status: str = "active") -> None:
        super().__init__()
        self.project_name = name
        self.project_status = status

    def compose(self) -> ComposeResult:
        icon = "●" if self.project_status == "active" else "○"
        yield Label(f"{icon} {self.project_name}")


class ProjectList(ListView):
    """Left panel: selectable list of projects."""

    def __init__(self) -> None:
        super().__init__()
        self.projects = []

    def on_mount(self) -> None:
        """Load projects when widget mounts."""
        self.load_projects()

    def load_projects(self) -> None:
        """Scan ~/ai/projects/ and load project list."""
        self.clear()
        self.projects = []

        if not PROJECTS_PATH.exists():
            return

        for project_dir in sorted(PROJECTS_PATH.iterdir()):
            if project_dir.is_dir() and not project_dir.name.startswith("."):
                # Check for project.md to get status
                status = "active"
                project_md = project_dir / "project.md"
                if project_md.exists():
                    content = project_md.read_text()
                    if "Status: archived" in content:
                        status = "archived"

                self.projects.append(project_dir.name)
                self.append(ProjectItem(project_dir.name, status))


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
        """Update display when project changes."""
        if not name:
            self.query_one("#detail-header", Static).update("Select a project")
            self.query_one("#detail-meta", Static).update("")
            self.query_one("#detail-progress", Static).update("")
            self.query_one("#detail-content", Static).update("")
            return

        self.query_one("#detail-header", Static).update(f"[bold]{name}[/bold]")

        # Load project details
        project_path = PROJECTS_PATH / name
        content_parts = []
        meta_parts = []

        # Read project.md for repo path
        project_md = project_path / "project.md"
        repo_path = None
        if project_md.exists():
            project_content = project_md.read_text()
            repo_path = parse_repo_path(project_content)

        # Get git branch
        if repo_path and repo_path.exists():
            branch = get_git_branch(repo_path)
            if branch:
                meta_parts.append(f"[cyan]Branch:[/cyan] {branch}")

        # Read session.md for What's Next and Recent Work
        session_md = project_path / "session.md"
        total_tasks = 0
        done_tasks = 0

        if session_md.exists():
            session_content = session_md.read_text()

            # Get last modified time
            mtime = datetime.fromtimestamp(session_md.stat().st_mtime)
            relative = get_relative_time(mtime)
            date_str = mtime.strftime("%b %d")
            meta_parts.append(f"[dim]{relative} ({date_str})[/dim]")

            # Count checkboxes for progress
            done_tasks = len(re.findall(r'\[x\]', session_content, re.IGNORECASE))
            undone_tasks = len(re.findall(r'\[ \]', session_content))
            total_tasks = done_tasks + undone_tasks

            # Extract What's Next
            whats_next = self._extract_section(session_content, "## What's Next")
            if whats_next:
                content_parts.append("[green]## What's Next[/green]")
                content_parts.append(whats_next)
                content_parts.append("")

            # Extract Recent Work
            recent_work = self._extract_section(session_content, "## Recent Work")
            if recent_work:
                content_parts.append("[blue]## Recent Work[/blue]")
                content_parts.append(recent_work)
                content_parts.append("")

        # Update meta line
        self.query_one("#detail-meta", Static).update("  ".join(meta_parts))

        # Update progress bar
        if total_tasks > 0:
            progress_pct = done_tasks / total_tasks
            bar_width = 20
            filled = int(bar_width * progress_pct)
            empty = bar_width - filled
            bar = "█" * filled + "░" * empty
            self.query_one("#detail-progress", Static).update(
                f"[green]{bar}[/green] {done_tasks}/{total_tasks} tasks"
            )
        else:
            self.query_one("#detail-progress", Static).update("")

        # Read gotchas.md
        gotchas_md = project_path / "gotchas.md"
        if gotchas_md.exists():
            gotchas_content = gotchas_md.read_text()
            # Get bullet points (lines starting with -)
            gotchas = [line for line in gotchas_content.split("\n")
                      if line.strip().startswith("-") or line.strip().startswith("•")]
            if gotchas:
                content_parts.append("[yellow]## Gotchas[/yellow]")
                content_parts.append("\n".join(gotchas[:5]))  # Limit to 5

        if content_parts:
            self.query_one("#detail-content", Static).update("\n".join(content_parts))
        else:
            self.query_one("#detail-content", Static).update("No session.md found")

    def _extract_section(self, content: str, header: str) -> str:
        """Extract content under a markdown header."""
        lines = content.split("\n")
        in_section = False
        section_lines = []

        for line in lines:
            if line.startswith(header):
                in_section = True
                continue
            elif in_section and line.startswith("## "):
                break
            elif in_section:
                if line.strip():
                    section_lines.append(line)

        return "\n".join(section_lines[:10])  # Limit lines


class AlertsPanel(Static):
    """Bottom panel: alerts and warnings."""

    def compose(self) -> ComposeResult:
        yield Static("No alerts", id="alerts-content")

    def check_alerts(self, projects: list[str]) -> None:
        """Check for issues and update alerts."""
        alerts = []

        for name in projects:
            project_path = PROJECTS_PATH / name

            # Check for missing files
            if not (project_path / "session.md").exists():
                alerts.append(f"⚠ {name}: missing session.md")
            if not (project_path / "gotchas.md").exists():
                alerts.append(f"⚠ {name}: missing gotchas.md")

            # Check for missing repo path
            project_md = project_path / "project.md"
            if project_md.exists():
                content = project_md.read_text()
                repo_path = parse_repo_path(content)
                if repo_path and not repo_path.exists():
                    alerts.append(f"⚠ {name}: repo path not found")

        if alerts:
            self.query_one("#alerts-content", Static).update("\n".join(alerts[:3]))
        else:
            self.query_one("#alerts-content", Static).update("✓ No alerts")


class HawkApp(App):
    """Main hawk-tui application."""

    TITLE = "hawk-tui"
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-rows: 1fr auto;
    }

    ProjectList {
        width: 25;
        border: solid green;
        padding: 0 1;
    }

    ProjectList > ListItem {
        padding: 0 1;
    }

    ProjectList > ListItem.--highlight {
        background: $accent;
    }

    #details {
        border: solid green;
        padding: 1;
    }

    #detail-header {
        text-style: bold;
    }

    #detail-meta {
        color: $text-muted;
        padding-bottom: 1;
    }

    #detail-progress {
        padding-bottom: 1;
    }

    #alerts {
        column-span: 2;
        height: auto;
        max-height: 5;
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
        Binding("e", "open_editor", "Editor"),
        Binding("enter", "select_project", "Open", show=False),
    ]

    current_project: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield ProjectList()
        yield DetailPanel(id="details")
        yield AlertsPanel(id="alerts")
        yield Footer()

    def on_mount(self) -> None:
        """Focus project list on start."""
        self.query_one(ProjectList).focus()
        # Check alerts after projects load
        self.set_timer(0.1, self._check_alerts)

    def _check_alerts(self) -> None:
        """Check alerts after mount."""
        project_list = self.query_one(ProjectList)
        alerts_panel = self.query_one(AlertsPanel)
        alerts_panel.check_alerts(project_list.projects)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle project selection."""
        if isinstance(event.item, ProjectItem):
            self.current_project = event.item.project_name
            detail_panel = self.query_one(DetailPanel)
            detail_panel.project_name = event.item.project_name

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Update details as user navigates."""
        if isinstance(event.item, ProjectItem):
            self.current_project = event.item.project_name
            detail_panel = self.query_one(DetailPanel)
            detail_panel.project_name = event.item.project_name

    def action_help(self) -> None:
        """Show help screen."""
        self.notify("Help: ↑↓ navigate, Enter session, e editor, q quit")

    def action_check(self) -> None:
        """Run integrity check."""
        self._check_alerts()
        self.notify("Integrity check complete")

    def action_sync(self) -> None:
        """Sync projects from ~/ai/projects."""
        project_list = self.query_one(ProjectList)
        project_list.load_projects()
        self._check_alerts()
        self.notify(f"Synced {len(project_list.projects)} projects")

    def action_select_project(self) -> None:
        """Handle Enter key on project - show tool selection."""
        if not self.current_project:
            self.notify("No project selected")
            return

        project_path = PROJECTS_PATH / self.current_project
        project_md = project_path / "project.md"

        if not project_md.exists():
            self.notify("No project.md found")
            return

        content = project_md.read_text()
        repo_path = parse_repo_path(content)

        if not repo_path or not repo_path.exists():
            self.notify("No valid repo path found")
            return

        def handle_tool_selection(tool: str) -> None:
            if tool:
                launch_iterm_session(repo_path, tool)
                self.notify(f"Launching {tool} for {self.current_project}")

        self.push_screen(ToolSelectScreen(), handle_tool_selection)

    def action_open_editor(self) -> None:
        """Open current project in editor."""
        if not self.current_project:
            self.notify("No project selected")
            return

        project_path = PROJECTS_PATH / self.current_project
        project_md = project_path / "project.md"

        if project_md.exists():
            content = project_md.read_text()
            repo_path = parse_repo_path(content)
            if repo_path and repo_path.exists():
                try:
                    subprocess.Popen(["code", str(repo_path)])
                    self.notify(f"Opening {self.current_project} in editor")
                except Exception as e:
                    self.notify(f"Failed to open editor: {e}")
            else:
                self.notify("No valid repo path found")
        else:
            self.notify("No project.md found")


def main():
    """Entry point for hawk-tui."""
    app = HawkApp()
    app.run()


if __name__ == "__main__":
    main()
