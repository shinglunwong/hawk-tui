"""Client data operations using TOML file."""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib

import tomli_w

CLIENTS_PATH = Path.home() / "ai" / "clients.toml"


@dataclass
class Client:
    id: str  # slug, e.g. "missionperform"
    name: str
    company: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    notes: str = ""
    billing_cycle: str = "annual"  # annual, monthly, one-time
    amount: int = 0  # in dollars
    currency: str = "CAD"
    next_payment: str = ""  # YYYY-MM-DD
    projects: list[str] = field(default_factory=list)

    def payment_status(self) -> str:
        """Return payment status: paid, due_soon, overdue, or none."""
        if not self.next_payment:
            return "none"
        try:
            next_date = date.fromisoformat(self.next_payment)
            today = date.today()
            days_until = (next_date - today).days
            if days_until < 0:
                return "overdue"
            elif days_until <= 14:
                return "due_soon"
            else:
                return "paid"
        except ValueError:
            return "none"

    def days_until_payment(self) -> Optional[int]:
        """Return days until next payment, negative if overdue."""
        if not self.next_payment:
            return None
        try:
            next_date = date.fromisoformat(self.next_payment)
            return (next_date - date.today()).days
        except ValueError:
            return None


def _load_clients() -> list[dict]:
    """Load clients from TOML file."""
    if not CLIENTS_PATH.exists():
        return []
    with open(CLIENTS_PATH, "rb") as f:
        data = tomllib.load(f)
    return data.get("clients", [])


def _save_clients(clients: list[dict]) -> None:
    """Save clients to TOML file."""
    CLIENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CLIENTS_PATH, "wb") as f:
        tomli_w.dump({"clients": clients}, f)


def _dict_to_client(d: dict) -> Client:
    """Convert dict to Client dataclass."""
    return Client(
        id=d.get("id", ""),
        name=d.get("name", ""),
        company=d.get("company", ""),
        email=d.get("email", ""),
        phone=d.get("phone", ""),
        address=d.get("address", ""),
        notes=d.get("notes", ""),
        billing_cycle=d.get("billing_cycle", "annual"),
        amount=d.get("amount", 0),
        currency=d.get("currency", "CAD"),
        next_payment=d.get("next_payment", ""),
        projects=d.get("projects", []),
    )


def _client_to_dict(c: Client) -> dict:
    """Convert Client to dict for TOML."""
    return asdict(c)


# --- Client CRUD ---

def get_all_clients() -> list[Client]:
    """Get all clients."""
    return [_dict_to_client(d) for d in _load_clients()]


def get_client(client_id: str) -> Optional[Client]:
    """Get a single client by ID."""
    for d in _load_clients():
        if d.get("id") == client_id:
            return _dict_to_client(d)
    return None


def create_client(client: Client) -> str:
    """Create a new client, return ID."""
    clients = _load_clients()
    clients.append(_client_to_dict(client))
    _save_clients(clients)
    return client.id


def update_client(client: Client) -> None:
    """Update an existing client."""
    clients = _load_clients()
    for i, d in enumerate(clients):
        if d.get("id") == client.id:
            clients[i] = _client_to_dict(client)
            break
    _save_clients(clients)


def delete_client(client_id: str) -> None:
    """Delete a client."""
    clients = [d for d in _load_clients() if d.get("id") != client_id]
    _save_clients(clients)


# --- Project-Client linking ---

def get_client_for_project(project_slug: str) -> Optional[Client]:
    """Get the client linked to a project."""
    for client in get_all_clients():
        if project_slug in client.projects:
            return client
    return None


def link_project_to_client(project_slug: str, client_id: str) -> None:
    """Link a project to a client."""
    clients = _load_clients()
    for d in clients:
        # Remove from other clients first
        if project_slug in d.get("projects", []):
            d["projects"].remove(project_slug)
        # Add to target client
        if d.get("id") == client_id:
            if "projects" not in d:
                d["projects"] = []
            if project_slug not in d["projects"]:
                d["projects"].append(project_slug)
    _save_clients(clients)


def unlink_project_from_client(project_slug: str) -> None:
    """Remove project from any client."""
    clients = _load_clients()
    for d in clients:
        if project_slug in d.get("projects", []):
            d["projects"].remove(project_slug)
    _save_clients(clients)


def get_projects_for_client(client_id: str) -> list[str]:
    """Get all project slugs linked to a client."""
    client = get_client(client_id)
    return client.projects if client else []


def get_upcoming_payments(days: int = 14) -> list[Client]:
    """Get clients with payments due within N days."""
    result = []
    for client in get_all_clients():
        status = client.payment_status()
        if status in ("due_soon", "overdue"):
            result.append(client)
    return result
