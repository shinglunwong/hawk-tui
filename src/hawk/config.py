from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

PROJECTS_PATH = Path.home() / "ai" / "projects"
CONFIG_PATH = Path.home() / "ai" / "projects" / "hawk-tui" / "data" / "config.toml"
ROUTINE_PATH = Path.home() / "ai" / "projects" / "hawk-tui" / "data" / "routine.md"

_config_cache: dict | None = None


def load_config() -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            _config_cache = tomllib.load(f)
    else:
        _config_cache = {
            "tools": {
                "ai_tools": ["claude", "opencode"],
                "default_ai_tool": "",
                "editor": "antigravity",
                "terminal": "iterm",
            },
            "paths": {"projects": "~/ai/projects"},
        }
    return _config_cache
