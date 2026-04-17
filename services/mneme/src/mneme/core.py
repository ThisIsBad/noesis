import sqlite3
from datetime import datetime
from typing import Optional

import chromadb

from noesis_schemas import Memory, MemoryType, ProofCertificate


class MnemeCore:
    def __init__(
        self,
        db_path: str = "mneme.db",
        chroma_path: str = "mneme_chroma",
        *,
        _chroma_client: Optional[chromadb.ClientAPI] = None,
    ) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._setup_schema()
        client = _chroma_client or chromadb.PersistentClient(path=chroma_path)
        self._col = client.get_or_create_collection("memories")

    def _setup_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                proven  INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS forget_log (
                memory_id   TEXT NOT NULL,
                reason      TEXT NOT NULL,
                forgotten_at TEXT NOT NULL
            );
        """)
        self._conn.commit()

    def store(
        self,
        content: str,
        memory_type: MemoryType,
        confidence: float = 0.5,
        certificate: Optional[ProofCertificate] = None,
        tags: Optional[list[str]] = None,
        source: Optional[str] = None,
    ) -> Memory:
        mem = Memory(
            content=content,
            memory_type=memory_type,
            confidence=confidence,
            certificate=certificate,
            proven=certificate.verified if certificate else False,
            tags=tags or [],
            source=source,
        )
        self._conn.execute(
            "INSERT INTO memories (memory_id, data_json, proven) VALUES (?, ?, ?)",
            (mem.memory_id, mem.model_dump_json(), int(mem.proven)),
        )
        self._conn.commit()
        self._col.add(
            ids=[mem.memory_id],
            documents=[content],
            metadatas=[{
                "confidence": confidence,
                "proven": int(mem.proven),
                "memory_type": memory_type.value,
            }],
        )
        return mem

    def retrieve(self, query: str, k: int = 5, min_confidence: float = 0.0) -> list[Memory]:
        count = self._col.count()
        if count == 0:
            return []
        # Over-fetch so confidence filtering doesn't cut us short
        results = self._col.query(
            query_texts=[query],
            n_results=min(max(k * 3, 10), count),
        )
        ids: list[str] = results["ids"][0]
        metadatas: list[dict] = results["metadatas"][0]  # type: ignore[assignment]

        filtered_ids = [
            mid for mid, meta in zip(ids, metadatas)
            if float(meta["confidence"]) >= min_confidence
        ][:k]

        memories: list[Memory] = []
        for mid in filtered_ids:
            row = self._conn.execute(
                "SELECT data_json FROM memories WHERE memory_id=?", (mid,)
            ).fetchone()
            if row:
                memories.append(Memory.model_validate_json(row[0]))
        return memories

    def forget(self, memory_id: str, reason: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM memories WHERE memory_id=?", (memory_id,)
        ).fetchone()
        if not row:
            return False
        self._conn.execute("DELETE FROM memories WHERE memory_id=?", (memory_id,))
        self._conn.execute(
            "INSERT INTO forget_log VALUES (?, ?, ?)",
            (memory_id, reason, datetime.utcnow().isoformat()),
        )
        self._conn.commit()
        self._col.delete(ids=[memory_id])
        return True

    def list_proven(self) -> list[Memory]:
        rows = self._conn.execute(
            "SELECT data_json FROM memories WHERE proven=1"
        ).fetchall()
        return [Memory.model_validate_json(r[0]) for r in rows]

    def consolidate(self, similarity_threshold: float = 0.15) -> int:
        """Merge near-duplicate memories; keeps the higher-confidence copy."""
        rows = self._conn.execute(
            "SELECT memory_id, data_json FROM memories"
        ).fetchall()
        if len(rows) < 2:
            return 0

        merged = 0
        deleted: set[str] = set()

        for memory_id, data_json in rows:
            if memory_id in deleted:
                continue
            remaining = self._col.count()
            if remaining < 2:
                break

            mem = Memory.model_validate_json(data_json)
            results = self._col.query(
                query_texts=[mem.content],
                n_results=min(2, remaining),
            )
            for other_id, dist in zip(results["ids"][0], results["distances"][0]):
                if other_id == memory_id or other_id in deleted:
                    continue
                if dist < similarity_threshold:
                    other_row = self._conn.execute(
                        "SELECT data_json FROM memories WHERE memory_id=?", (other_id,)
                    ).fetchone()
                    if not other_row:
                        continue
                    other = Memory.model_validate_json(other_row[0])
                    to_delete = other_id if mem.confidence >= other.confidence else memory_id
                    to_keep = memory_id if to_delete == other_id else other_id
                    self.forget(to_delete, f"consolidated into {to_keep}")
                    deleted.add(to_delete)
                    merged += 1
                    break

        return merged
