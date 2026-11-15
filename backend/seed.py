"""Synthetic seed data. Every row is simulated; no real person or address."""
from __future__ import annotations

from backend.db import Database

CUSTOMERS = [
    dict(
        id="CUST_001", name="Asha (synthetic)", language="kn", meeting_mode=1,
        window_start="18:00", window_end="20:00", allow_guard=0, allow_neighbor=0,
        area="Demo Layout, Block 4 (mock)", landmark="opposite the blue water tank (mock)",
    ),
]

ORDERS = [
    dict(id="ORD_1024", customer_id="CUST_001", store="Demo Store", status="out_for_delivery", requires_otp=0),
    dict(id="ORD_2048", customer_id="CUST_001", store="Demo Store", status="out_for_delivery", requires_otp=1),
    dict(id="ORD_9999", customer_id="CUST_001", store="Demo Store", status="delivered", requires_otp=0),
]


def seed(db: Database, reset: bool = False) -> None:
    if reset:
        db.execute("DELETE FROM orders")
        db.execute("DELETE FROM customers")
    for c in CUSTOMERS:
        db.execute(
            "INSERT OR IGNORE INTO customers (id,name,language,meeting_mode,window_start,window_end,"
            "allow_guard,allow_neighbor,area,landmark,simulated) VALUES (?,?,?,?,?,?,?,?,?,?,1)",
            (c["id"], c["name"], c["language"], c["meeting_mode"], c["window_start"], c["window_end"],
             c["allow_guard"], c["allow_neighbor"], c["area"], c["landmark"]),
        )
    for o in ORDERS:
        db.execute(
            "INSERT OR IGNORE INTO orders (id,customer_id,store,status,requires_otp,simulated) VALUES (?,?,?,?,?,1)",
            (o["id"], o["customer_id"], o["store"], o["status"], o["requires_otp"]),
        )


if __name__ == "__main__":
    from backend.config import settings

    d = Database(settings.db_path)
    seed(d)
    print("seeded", d.all("SELECT id, requires_otp, status FROM orders"))
