import subprocess
from datetime import datetime
from pathlib import Path


def get_git_branch(repo_path: Path) -> str:
    if not repo_path.exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def get_relative_time(dt: datetime) -> str:
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
    for line in content.split("\n"):
        if line.startswith("Repo:"):
            path_str = line.replace("Repo:", "").strip()
            if path_str.startswith("~"):
                path_str = str(Path.home()) + path_str[1:]
            return Path(path_str)
    return None


def launch_iterm_session(repo_path: Path, tool: str) -> None:
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
            write text "cd \\"{path_str}\\" && {tool} --prompt \\"read session context\\""
            set rightPane to (split vertically with default profile)
        end tell
        tell rightPane
            write text "cd \\"{path_str}\\""
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script])
