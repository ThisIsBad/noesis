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
        return self.store_batch([(
            content, memory_type, confidence, certificate, tags, source,
        )])[0]

    def store_batch(
        self,
        items: list[
            tuple[
                str,
                MemoryType,
                float,
                Optional[ProofCertificate],
                Optional[list[str]],
                Optional[str],
            ]
        ],
    ) -> list[Memory]:
        """Batch-store memories in one SQLite transaction + one Chroma add.

        Each item is a tuple ``(content, memory_type, confidence,
        certificate, tags, source)`` matching `store`'s signature. The
        default embedder amortises tokenisation and ONNX inference
        across the batch, which is dramatically cheaper than calling
        `store` in a loop.
        """
        if not items:
            return []
        memories: list[Memory] = []
        rows: list[tuple[str, str, int]] = []
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, object]] = []
        for content, memory_type, confidence, certificate, tags, source in items:
            mem = Memory(
                content=content,
                memory_type=memory_type,
                confidence=confidence,
                certificate=certificate,
                proven=certificate.verified if certificate else False,
                tags=tags or [],
                source=source,
            )
            memories.append(mem)
            rows.append((mem.memory_id, mem.model_dump_json(), int(mem.proven)))
            ids.append(mem.memory_id)
            documents.append(content)
            metadatas.append({
                "confidence": confidence,
                "proven": int(mem.proven),
                "memory_type": memory_type.value,
            })
        self._conn.executemany(
            "INSERT INTO memories (memory_id, data_json, proven) VALUES (?, ?, ?)",
            rows,
        )
        self._conn.commit()
        self._col.add(ids=ids, documents=documents, metadatas=metadatas)
        return memories

    def retrieve(
        self, query: str, k: int = 5, min_confidence: float = 0.0
    ) -> list[Memory]:
        return self.retrieve_batch([query], k=k, min_confidence=min_confidence)[0]

    def retrieve_batch(
        self,
        queries: list[str],
        k: int = 5,
        min_confidence: float = 0.0,
    ) -> list[list[Memory]]:
        """Batch version of `retrieve`: one ChromaDB round-trip for all queries.

        Far cheaper than calling `retrieve` in a loop — the default embedder
        amortises tokenisation and ONNX inference across the batch. Returns
        results aligned with the input `queries` list.
        """
        if not queries:
            return []
        count = self._col.count()
        if count == 0:
            return [[] for _ in queries]
        results = self._col.query(
            query_texts=queries,
            n_results=min(max(k * 3, 10), count),
        )
        out: list[list[Memory]] = []
        for ids, metadatas in zip(results["ids"], results["metadatas"]):
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
            out.append(memories)
        return out

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
                    to_delete = (
                        other_id if mem.confidence >= other.confidence else memory_id
                    )
                    to_keep = memory_id if to_delete == other_id else other_id
                    self.forget(to_delete, f"consolidated into {to_keep}")
                    deleted.add(to_delete)
                    merged += 1
                    break

        return merged
