"""Legacy wrapper for FOL checker.

Prefer: `python tools/check_fol_results.py`
"""

from __future__ import annotations

from tools.check_fol_results import main


if __name__ == "__main__":
    print("[DEPRECATED] Use: python tools/check_fol_results.py")
    raise SystemExit(main())
