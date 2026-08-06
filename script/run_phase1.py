from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipelines.phase1 import main


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("[*] Starting Phase 1 Baseline Pipeline (ETL -> Gate -> Index -> Evaluate -> Report)...")
    main()
    print("[✓] Phase 1 Baseline Pipeline completed successfully!")
    print("[i] Check results in data/results/, data/quality/, and data/reports/")
