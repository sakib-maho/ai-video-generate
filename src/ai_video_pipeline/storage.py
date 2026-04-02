from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from .models import TopicCandidate, to_dict
from .utils import ensure_dir


class Storage:
    def __init__(self, database_path: Path) -> None:
        ensure_dir(database_path.parent)
        self.database_path = database_path
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    summary_json TEXT
                );

                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    country TEXT NOT NULL,
                    title TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    trend_score REAL NOT NULL,
                    freshness_score REAL NOT NULL,
                    suitability_score REAL NOT NULL,
                    risk_score REAL NOT NULL,
                    risk_flags_json TEXT NOT NULL,
                    fact_check_status TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    why_trending TEXT NOT NULL,
                    selected INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'discovered'
                );

                CREATE INDEX IF NOT EXISTS idx_topics_signature_country ON topics(signature, country);
                CREATE INDEX IF NOT EXISTS idx_topics_run_date ON topics(run_date);

                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    country TEXT NOT NULL,
                    topic_title TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    final_video_path TEXT,
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    country TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    upload_date TEXT,
                    views INTEGER,
                    likes INTEGER,
                    comments INTEGER,
                    watch_time REAL,
                    ctr REAL,
                    retention REAL,
                    metadata_json TEXT NOT NULL
                );
                """
            )

    def create_run(self, run_date: str, mode: str) -> int:
        started_at = datetime.now().astimezone().isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO runs(run_date, mode, status, started_at) VALUES (?, ?, ?, ?)",
                (run_date, mode, "running", started_at),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, summary: dict) -> None:
        finished_at = datetime.now().astimezone().isoformat()
        with self.connect() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, finished_at = ?, summary_json = ? WHERE id = ?",
                (status, finished_at, json.dumps(summary, ensure_ascii=False), run_id),
            )

    def record_candidate(self, run_date: str, candidate: TopicCandidate, selected: bool = False, status: str = "discovered") -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO topics(
                    run_date, country, title, signature, trend_score, freshness_score, suitability_score,
                    risk_score, risk_flags_json, fact_check_status, citations_json, sources_json,
                    why_trending, selected, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_date,
                    candidate.country,
                    candidate.title,
                    candidate.signature,
                    candidate.trend_score,
                    candidate.freshness_score,
                    candidate.suitability_score,
                    candidate.risk_score,
                    json.dumps(candidate.risk_flags, ensure_ascii=False),
                    candidate.fact_check_status,
                    json.dumps(candidate.citations, ensure_ascii=False),
                    json.dumps([to_dict(source) for source in candidate.sources], ensure_ascii=False),
                    candidate.why_trending,
                    1 if selected else 0,
                    status,
                ),
            )

    def was_recently_used(self, signature: str, country: str, cooldown_days: int) -> bool:
        cutoff = (datetime.now().astimezone() - timedelta(days=cooldown_days)).date().isoformat()
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM topics
                WHERE signature = ? AND country = ? AND selected = 1 AND run_date >= ?
                LIMIT 1
                """,
                (signature, country, cutoff),
            ).fetchone()
        return row is not None

    def record_artifact(self, run_date: str, country: str, topic_title: str, metadata: dict, final_video_path: str | None, status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO artifacts(run_date, country, topic_title, metadata_json, final_video_path, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_date, country, topic_title, json.dumps(metadata, ensure_ascii=False), final_video_path, status),
            )

    def get_latest_review_packet(self, run_date: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT summary_json FROM runs WHERE run_date = ? ORDER BY id DESC LIMIT 1",
                (run_date,),
            ).fetchone()
