"""Empiria — experience accumulation and lesson retrieval.

Production-shaped persistence: SQLite for structured ``Lesson`` rows,
ChromaDB for semantic retrieval keyed on ``context + lesson_text``.
Mirrors Techne's storage split (which itself mirrors Mneme's), so the
ops story — data dir, volume mount, optional ``<SVC>_DATABASE_URL``
override — is consistent across the three stateful services.

A ``Lesson`` carries:

- **context / action_taken / outcome / lesson_text** — what happened
  and what to remember about it.
- **success** — boolean win/loss flag for the action; used by
  ``successful_patterns`` to surface only the wins.
- **confidence** — subjective belief in the lesson, in [0, 1]. Lifts a
  lesson's ranking inside ``retrieve`` so high-confidence lessons surface
  above marginally-better-matching low-confidence ones.
- **domain** — optional namespace for scoped retrieval.
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import chromadb
from noesis_schemas import Lesson

if TYPE_CHECKING:  # pragma: no cover
    from chromadb.api import ClientAPI


class EmpiriaCore:
    """Lesson library backed by SQLite + ChromaDB.

    Callers should supply ``db_path`` and ``chroma_path`` pointing at
    writable storage; the MCP server reads both from ``EMPIRIA_DATA_DIR``
    (or the new ``EMPIRIA_DATABASE_URL`` via
    ``noesis_clients.persistence``). For tests, passing
    ``_chroma_client=chromadb.EphemeralClient()`` gives an in-memory
    Chroma without touching disk.
    """

    def __init__(
        self,
        db_path: str = "empiria.db",
        chroma_path: str = "empiria_chroma",
        *,
        _chroma_client: ClientAPI | None = None,
    ) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._setup_schema()
        client = _chroma_client or chromadb.PersistentClient(path=chroma_path)
        self._col = client.get_or_create_collection("lessons")

    def _setup_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS lessons (
                lesson_id   TEXT PRIMARY KEY,
                data_json   TEXT NOT NULL,
                success     INTEGER NOT NULL DEFAULT 0,
                confidence  REAL    NOT NULL DEFAULT 0.0,
                domain      TEXT
            );
            """
        )
        self._conn.commit()

    # ── writes ─────────────────────────────────────────────────────────

    def record(
        self,
        context: str,
        action_taken: str,
        outcome: str,
        success: bool,
        lesson_text: str,
        confidence: float = 0.5,
        domain: str | None = None,
    ) -> Lesson:
        lesson = Lesson(
            context=context,
            action_taken=action_taken,
            outcome=outcome,
            success=success,
            lesson_text=lesson_text,
            confidence=confidence,
            domain=domain,
        )
        self._conn.execute(
            "INSERT INTO lessons "
            "(lesson_id, data_json, success, confidence, domain) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                lesson.lesson_id,
                lesson.model_dump_json(),
                int(lesson.success),
                lesson.confidence,
                lesson.domain,
            ),
        )
        self._conn.commit()
        # Index by context + lesson_text. ``action_taken`` and ``outcome``
        # often contain tool names / system strings that match
        # false-positive on context queries; keep them out of the embedding.
        self._col.add(
            ids=[lesson.lesson_id],
            documents=[f"{context}. {lesson_text}"],
            metadatas=[
                {
                    "success": int(lesson.success),
                    "domain": domain or "",
                }
            ],
        )
        return lesson

    # ── reads ──────────────────────────────────────────────────────────

    def retrieve(
        self,
        context: str,
        k: int = 5,
        domain: str | None = None,
    ) -> list[Lesson]:
        """Semantic k-nearest on ``context + lesson_text``, then rank by confidence.

        Chroma gives us relevance; we re-sort the top candidates by
        recorded confidence so a high-belief lesson with marginally lower
        embedding similarity outranks a marginally-better-matching
        low-belief one. Returns at most ``k`` results.
        """
        count = self._col.count()
        if count == 0:
            return []
        where = {"domain": domain} if domain else None
        fetch_k = min(max(k * 3, 10), count)
        results = self._col.query(
            query_texts=[context],
            n_results=fetch_k,
            where=where,
        )
        ids: list[str] = results["ids"][0] if results["ids"] else []
        if not ids:
            return []
        placeholders = ",".join(["?"] * len(ids))
        rows = self._conn.execute(
            f"SELECT data_json FROM lessons WHERE lesson_id IN ({placeholders})",
            ids,
        ).fetchall()
        lessons = [Lesson.model_validate_json(row[0]) for row in rows]
        lessons.sort(key=lambda lesson: lesson.confidence, reverse=True)
        return lessons[:k]

    def successful_patterns(
        self, domain: str | None = None
    ) -> list[Lesson]:
        """Return every recorded lesson whose ``success`` is true."""
        if domain is None:
            rows = self._conn.execute(
                "SELECT data_json FROM lessons WHERE success=1"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT data_json FROM lessons WHERE success=1 AND domain=?",
                (domain,),
            ).fetchall()
        return [Lesson.model_validate_json(row[0]) for row in rows]

    def get(self, lesson_id: str) -> Lesson | None:
        """Return a stored lesson by id, or None if it doesn't exist."""
        row = self._conn.execute(
            "SELECT data_json FROM lessons WHERE lesson_id=?", (lesson_id,)
        ).fetchone()
        if row is None:
            return None
        return Lesson.model_validate_json(row[0])
