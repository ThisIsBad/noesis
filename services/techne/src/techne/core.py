"""Techne — verified skill library.

Production-shaped persistence: SQLite for structured skill rows,
ChromaDB for semantic retrieval keyed on ``name + description``.
Mirrors Mneme's storage split (SQLite for records, Chroma for
nearest-neighbour search) so the ops story is consistent across the
two services that actually persist state.

A ``Skill`` carries:

- **name / description / strategy** — what the skill is and how it
  works.
- **certificate** — optional ``ProofCertificate`` from Logos;
  ``verified`` on the skill is a mirror of the certificate's
  ``verified`` bit so retrieval can filter without re-parsing the
  certificate.
- **use_count / success_rate** — running counts updated by
  ``record_use``; success rate lifts a skill's ranking inside
  ``retrieve`` so proven-good skills surface first.
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import chromadb
from noesis_schemas import ProofCertificate, Skill

if TYPE_CHECKING:  # pragma: no cover
    from chromadb.api import ClientAPI


class TechneCore:
    """Skill library backed by SQLite + ChromaDB.

    Callers should supply ``db_path`` and ``chroma_path`` pointing at
    writable storage; the MCP server reads both from ``TECHNE_DATA_DIR``
    (or the new ``TECHNE_DATABASE_URL`` via
    ``noesis_clients.persistence``). For tests, passing
    ``_chroma_client=chromadb.EphemeralClient()`` gives an in-memory
    Chroma without touching disk.
    """

    def __init__(
        self,
        db_path: str = "techne.db",
        chroma_path: str = "techne_chroma",
        *,
        _chroma_client: ClientAPI | None = None,
    ) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._setup_schema()
        client = _chroma_client or chromadb.PersistentClient(path=chroma_path)
        self._col = client.get_or_create_collection("skills")

    def _setup_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS skills (
                skill_id     TEXT PRIMARY KEY,
                data_json    TEXT NOT NULL,
                verified     INTEGER NOT NULL DEFAULT 0,
                success_rate REAL    NOT NULL DEFAULT 0.0,
                use_count    INTEGER NOT NULL DEFAULT 0,
                domain       TEXT
            );
            """
        )
        self._conn.commit()

    # ── writes ─────────────────────────────────────────────────────────

    def store(
        self,
        name: str,
        description: str,
        strategy: str,
        certificate: ProofCertificate | None = None,
        domain: str | None = None,
    ) -> Skill:
        skill = Skill(
            name=name,
            description=description,
            strategy=strategy,
            verified=certificate.verified if certificate else False,
            certificate=certificate,
            domain=domain,
        )
        self._conn.execute(
            "INSERT INTO skills "
            "(skill_id, data_json, verified, success_rate, use_count, domain) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                skill.skill_id,
                skill.model_dump_json(),
                int(skill.verified),
                skill.success_rate,
                skill.use_count,
                skill.domain,
            ),
        )
        self._conn.commit()
        # Index by name + description for semantic search. Strategy text
        # often contains tool names that match false-positive on queries
        # about the skill's purpose; keep it out of the embedding.
        self._col.add(
            ids=[skill.skill_id],
            documents=[f"{name}. {description}"],
            metadatas=[
                {
                    "verified": int(skill.verified),
                    "domain": domain or "",
                }
            ],
        )
        return skill

    def record_use(self, skill_id: str, success: bool) -> Skill:
        skill = self._load(skill_id)
        if skill is None:
            raise KeyError(skill_id)
        total = skill.use_count + 1
        delta = 1.0 if success else 0.0
        skill.success_rate = (
            skill.success_rate * skill.use_count + delta
        ) / total
        skill.use_count = total
        self._conn.execute(
            "UPDATE skills "
            "SET data_json=?, success_rate=?, use_count=? "
            "WHERE skill_id=?",
            (
                skill.model_dump_json(),
                skill.success_rate,
                skill.use_count,
                skill_id,
            ),
        )
        self._conn.commit()
        return skill

    # ── reads ──────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        k: int = 5,
        verified_only: bool = False,
    ) -> list[Skill]:
        """Semantic k-nearest on ``name + description``, then rank by success_rate.

        Chroma gives us relevance; we re-sort the top candidates by
        observed success rate so a proven skill with marginally lower
        embedding similarity outranks an untested better-matching
        one. Returns at most ``k`` results.
        """
        count = self._col.count()
        if count == 0:
            return []
        where = {"verified": 1} if verified_only else None
        fetch_k = min(max(k * 3, 10), count)
        results = self._col.query(
            query_texts=[query],
            n_results=fetch_k,
            where=where,
        )
        ids: list[str] = results["ids"][0] if results["ids"] else []
        if not ids:
            return []
        placeholders = ",".join(["?"] * len(ids))
        rows = self._conn.execute(
            f"SELECT data_json FROM skills WHERE skill_id IN ({placeholders})",
            ids,
        ).fetchall()
        skills = [Skill.model_validate_json(row[0]) for row in rows]
        skills.sort(key=lambda s: s.success_rate, reverse=True)
        return skills[:k]

    def get(self, skill_id: str) -> Skill | None:
        """Return a stored skill by id, or None if it doesn't exist."""
        return self._load(skill_id)

    # ── internals ──────────────────────────────────────────────────────

    def _load(self, skill_id: str) -> Skill | None:
        row = self._conn.execute(
            "SELECT data_json FROM skills WHERE skill_id=?", (skill_id,)
        ).fetchone()
        if row is None:
            return None
        return Skill.model_validate_json(row[0])
