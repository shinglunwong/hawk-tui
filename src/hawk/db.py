"""Database operations for hawk-tui."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / "ai" / "projects" / "hawk-tui" / "data" / "hawk.db"


@dataclass
class Client:
    id: Optional[int]
    name: str
    email: str = ""
    company: str = ""
    phone: str = ""
    address: str = ""
    notes: str = ""


def get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT DEFAULT '',
            company TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_clients (
            project_slug TEXT NOT NULL,
            client_id INTEGER NOT NULL,
            PRIMARY KEY (project_slug, client_id),
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        )
    """)
    conn.commit()


# --- Client CRUD ---

def get_all_clients() -> list[Client]:
    """Get all clients."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    conn.close()
    return [Client(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        company=row["company"],
        phone=row["phone"],
        address=row["address"],
        notes=row["notes"],
    ) for row in rows]


def get_client(client_id: int) -> Optional[Client]:
    """Get a single client by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return Client(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        company=row["company"],
        phone=row["phone"],
        address=row["address"],
        notes=row["notes"],
    )


def create_client(client: Client) -> int:
    """Create a new client, return ID."""
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO clients (name, email, company, phone, address, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (client.name, client.email, client.company, client.phone, client.address, client.notes)
    )
    conn.commit()
    client_id = cursor.lastrowid
    conn.close()
    return client_id


def update_client(client: Client) -> None:
    """Update an existing client."""
    conn = get_connection()
    conn.execute(
        "UPDATE clients SET name=?, email=?, company=?, phone=?, address=?, notes=? WHERE id=?",
        (client.name, client.email, client.company, client.phone, client.address, client.notes, client.id)
    )
    conn.commit()
    conn.close()


def delete_client(client_id: int) -> None:
    """Delete a client."""
    conn = get_connection()
    conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    conn.commit()
    conn.close()


# --- Project-Client linking ---

def get_client_for_project(project_slug: str) -> Optional[Client]:
    """Get the client linked to a project."""
    conn = get_connection()
    row = conn.execute("""
        SELECT c.* FROM clients c
        JOIN project_clients pc ON c.id = pc.client_id
        WHERE pc.project_slug = ?
    """, (project_slug,)).fetchone()
    conn.close()
    if not row:
        return None
    return Client(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        company=row["company"],
        phone=row["phone"],
        address=row["address"],
        notes=row["notes"],
    )


def link_project_to_client(project_slug: str, client_id: int) -> None:
    """Link a project to a client."""
    conn = get_connection()
    conn.execute("DELETE FROM project_clients WHERE project_slug = ?", (project_slug,))
    conn.execute("INSERT INTO project_clients (project_slug, client_id) VALUES (?, ?)", (project_slug, client_id))
    conn.commit()
    conn.close()


def unlink_project_from_client(project_slug: str) -> None:
    """Remove client link from project."""
    conn = get_connection()
    conn.execute("DELETE FROM project_clients WHERE project_slug = ?", (project_slug,))
    conn.commit()
    conn.close()


def get_projects_for_client(client_id: int) -> list[str]:
    """Get all project slugs linked to a client."""
    conn = get_connection()
    rows = conn.execute("SELECT project_slug FROM project_clients WHERE client_id = ?", (client_id,)).fetchall()
    conn.close()
    return [row["project_slug"] for row in rows]
