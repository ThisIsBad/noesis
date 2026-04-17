"""External benchmark integration — notes and adapters.

Internal module — not part of the public API (Tier 3).

Useful external benchmarks for LLM logic evaluation:

1. **SATBench** (Apache 2.0, HuggingFace)
   - 2100 SAT/UNSAT puzzles in JSONL format
   - Download: https://huggingface.co/datasets/LLM4Code/SATBench
   - File: SATBench-problems.jsonl
   - Each problem has natural language scenario + SAT/UNSAT label

2. **FOLIO** (Yale NLP, requires HuggingFace login)
   - 1430 first-order logic NLI problems
   - Download: https://huggingface.co/datasets/yale-nlp/FOLIO
   - Premises + conclusion + label (True/False/Unknown)

3. **ProntoQA** (Open, GitHub)
   - Synthetic chain-of-thought reasoning problems
   - Download: https://github.com/asaparov/prontoqa
   - Tests deductive reasoning over ontologies

4. **LogicNLI** (Open, HuggingFace)
   - NLI-style first-order logic dataset
   - Download: https://huggingface.co/datasets/tasksource/LogicNLI

5. **Rosetta-PL** (2025, arXiv)
   - Propositional logic translation benchmark
   - Tests generalization to custom logical languages
"""

from __future__ import annotations

__all__ = ["load_satbench", "load_folio"]

import json
from pathlib import Path
from typing import Any


def load_satbench(jsonl_path: Path) -> list[dict[str, Any]]:
    """Load SATBench problems from a JSONL file.

    Each problem is a dict with keys:
      - scenario: str (natural language context)
      - conditions: list[str] (logical conditions)
      - question: str (the question to answer)
      - label: str ("SAT" or "UNSAT")

    Returns list of standardized problem dicts.
    """
    problems = []
    with open(jsonl_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            raw = json.loads(line)
            problems.append({
                "id": f"SAT-{i+1:04d}",
                "source": "SATBench",
                "level": "external",
                "category": "sat_puzzle",
                "natural_language": _format_satbench_problem(raw),
                "expected_satisfiable": raw.get("label", "").upper() == "SAT",
                "raw": raw,
            })
    return problems


def _format_satbench_problem(raw: dict[str, Any]) -> str:
    """Format a SATBench problem as a single natural language string."""
    parts = []
    if "scenario" in raw:
        parts.append(raw["scenario"])
    if "conditions" in raw:
        parts.append("Conditions:")
        for i, cond in enumerate(raw["conditions"], 1):
            parts.append(f"  {i}. {cond}")
    if "question" in raw:
        parts.append(f"Question: {raw['question']}")
    return "\n".join(parts)


def load_folio(jsonl_path: Path) -> list[dict[str, Any]]:
    """Load FOLIO problems from a JSONL file.

    Each problem has:
      - premises: list[str]
      - conclusion: str
      - label: "True" | "False" | "Unknown"
    """
    problems = []
    with open(jsonl_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            raw = json.loads(line)
            problems.append({
                "id": f"FOLIO-{i+1:04d}",
                "source": "FOLIO",
                "level": "external",
                "category": "first_order_nli",
                "natural_language": _format_folio_problem(raw),
                "expected_label": raw.get("label", "Unknown"),
                "raw": raw,
            })
    return problems


def _format_folio_problem(raw: dict[str, Any]) -> str:
    """Format a FOLIO problem as natural language."""
    parts = []
    if "premises" in raw:
        parts.append("Premises:")
        for p in raw["premises"]:
            parts.append(f"  - {p}")
    if "conclusion" in raw:
        parts.append(f"Conclusion: {raw['conclusion']}")
    return "\n".join(parts)
