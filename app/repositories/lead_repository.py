import sqlite3
from typing import Optional
from app.core.config import get_settings
from app.models.lead import Lead


class LeadRepository:
    def __init__(self) -> None:
        self.db_path = get_settings().sqlite_db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cellnumber TEXT NOT NULL UNIQUE,
                    name TEXT,
                    mattress_size TEXT,
                    need TEXT,
                    budget_range TEXT,
                    city TEXT,
                    urgency TEXT,
                    status TEXT NOT NULL DEFAULT 'open'
                )
                """
            )
            conn.commit()

    def get_by_cellnumber(self, cellnumber: str) -> Optional[Lead]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, cellnumber, name, mattress_size, need, budget_range, city, urgency, status FROM leads WHERE cellnumber = ?",
                (cellnumber,),
            ).fetchone()
        if not row:
            return None
        return Lead(*row)

    def upsert(self, lead: Lead) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO leads (cellnumber, name, mattress_size, need, budget_range, city, urgency, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cellnumber) DO UPDATE SET
                    name=excluded.name,
                    mattress_size=excluded.mattress_size,
                    need=excluded.need,
                    budget_range=excluded.budget_range,
                    city=excluded.city,
                    urgency=excluded.urgency,
                    status=excluded.status
                """,
                (
                    lead.cellnumber,
                    lead.name,
                    lead.mattress_size,
                    lead.need,
                    lead.budget_range,
                    lead.city,
                    lead.urgency,
                    lead.status,
                ),
            )
            conn.commit()
