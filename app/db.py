import os
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kora.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchants (
                id TEXT PRIMARY KEY,
                phone TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY,
                merchant_id TEXT NOT NULL,
                amount REAL NOT NULL,
                customer_name TEXT,
                description TEXT,
                reference TEXT UNIQUE NOT NULL,
                payment_link TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (merchant_id) REFERENCES merchants(id)
            )
        """)
        conn.commit()


def get_or_create_merchant(phone: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM merchants WHERE phone = ?", (phone,)).fetchone()
        if row:
            return dict(row)
        merchant_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO merchants (id, phone, created_at) VALUES (?, ?, ?)",
            (merchant_id, phone, now),
        )
        conn.commit()
        return {"id": merchant_id, "phone": phone, "created_at": now}


def create_payment(merchant_id: str, amount: float, customer_name: str = None, description: str = None) -> dict:
    payment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO payments
               (id, merchant_id, amount, customer_name, description, reference, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (payment_id, merchant_id, amount, customer_name, description, payment_id, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        return dict(row)


def update_payment(reference: str, status: str, payment_link: str = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        if payment_link:
            conn.execute(
                "UPDATE payments SET status = ?, payment_link = ?, updated_at = ? WHERE reference = ?",
                (status, payment_link, now, reference),
            )
        else:
            conn.execute(
                "UPDATE payments SET status = ?, updated_at = ? WHERE reference = ?",
                (status, now, reference),
            )
        conn.commit()


def get_payment_by_reference(reference: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM payments WHERE reference = ?", (reference,)).fetchone()
        return dict(row) if row else None


def get_payments_for_period(merchant_id: str, period: str) -> list:
    today = datetime.now(timezone.utc).date()
    if period == "daily":
        start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc).isoformat()
    elif period == "weekly":
        start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    elif period == "monthly":
        start = datetime(today.year, today.month, 1, tzinfo=timezone.utc).isoformat()
    elif period == "quarterly":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start = datetime(today.year, quarter_start_month, 1, tzinfo=timezone.utc).isoformat()
    elif period == "yearly":
        start = datetime(today.year, 1, 1, tzinfo=timezone.utc).isoformat()
    else:
        start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc).isoformat()

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM payments WHERE merchant_id = ? AND created_at >= ? ORDER BY created_at ASC",
            (merchant_id, start),
        ).fetchall()
    return [dict(r) for r in rows]


def get_summary(merchant_id: str, period: str) -> dict:
    today = datetime.now(timezone.utc).date()
    if period == "daily":
        start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc).isoformat()
    elif period == "weekly":
        start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    elif period == "monthly":
        start = datetime(today.year, today.month, 1, tzinfo=timezone.utc).isoformat()
    elif period == "quarterly":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start = datetime(today.year, quarter_start_month, 1, tzinfo=timezone.utc).isoformat()
    elif period == "yearly":
        start = datetime(today.year, 1, 1, tzinfo=timezone.utc).isoformat()
    else:
        start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc).isoformat()

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM payments WHERE merchant_id = ? AND created_at >= ?",
            (merchant_id, start),
        ).fetchall()

    payments = [dict(r) for r in rows]
    successful = [p for p in payments if p["status"] == "completed"]
    failed = [p for p in payments if p["status"] == "failed"]
    pending = [p for p in payments if p["status"] == "pending"]

    return {
        "period": period,
        "total_revenue": sum(p["amount"] for p in successful),
        "successful": len(successful),
        "failed": len(failed),
        "pending": len(pending),
    }
