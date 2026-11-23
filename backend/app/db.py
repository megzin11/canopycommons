"""SQLite persistence for participatory citizen feedback and stratified NEB aggregation."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.app.optimizer import aggregate_stratified_neb_weights
from backend.app.schemas import CityKey, FeedbackRecord, FeedbackSubmission, NEBWeights

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "canopycommons.db"


def _connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stakeholder_feedback (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT NOT NULL,
                h3_index TEXT NOT NULL,
                stratum TEXT NOT NULL,
                persona_role TEXT NOT NULL,
                priority_tag TEXT NOT NULL,
                rationale_text TEXT NOT NULL,
                points_sustainable INTEGER NOT NULL,
                points_beautiful INTEGER NOT NULL,
                points_together INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def insert_feedback(
    sub: FeedbackSubmission, db_path: Path = DEFAULT_DB_PATH
) -> FeedbackRecord:
    init_db(db_path)
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO stakeholder_feedback (
                city, h3_index, stratum, persona_role, priority_tag, rationale_text,
                points_sustainable, points_beautiful, points_together, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sub.city,
                sub.h3_index,
                sub.stratum,
                sub.persona_role,
                sub.priority_tag,
                sub.rationale_text,
                sub.points_sustainable,
                sub.points_beautiful,
                sub.points_together,
                created_at,
            ),
        )
        conn.commit()
        fid = int(cur.lastrowid)

    return FeedbackRecord(feedback_id=fid, created_at=created_at, **sub.model_dump())


def list_feedback(
    city: CityKey, db_path: Path = DEFAULT_DB_PATH
) -> list[FeedbackRecord]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM stakeholder_feedback
            WHERE city = ?
            ORDER BY feedback_id DESC
            """,
            (city,),
        ).fetchall()
    return [FeedbackRecord(**dict(r)) for r in rows]


def get_feedback_cell_boosts(
    city: CityKey, db_path: Path = DEFAULT_DB_PATH
) -> dict[str, int]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT h3_index, COUNT(*) AS cnt
            FROM stakeholder_feedback
            WHERE city = ?
            GROUP BY h3_index
            """,
            (city,),
        ).fetchall()
    return {str(r["h3_index"]): int(r["cnt"]) for r in rows}


def get_stratified_citizen_weights(
    city: CityKey,
    db_path: Path = DEFAULT_DB_PATH,
    stratum_shares: dict[str, float] | None = None,
) -> NEBWeights | None:
    records = list_feedback(city, db_path=db_path)
    if not records:
        return None
    grouped: dict[str, list[tuple[int, int, int]]] = {}
    for rec in records:
        grouped.setdefault(rec.stratum, []).append(
            (rec.points_sustainable, rec.points_beautiful, rec.points_together)
        )
    return aggregate_stratified_neb_weights(grouped, stratum_shares=stratum_shares)