from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipelines.corruption_flow import main


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("[*] Starting Phase 2 Corruption & Repair Flow (Corrupt -> Evaluate -> Repair -> Re-evaluate -> Compare)...")
    main()
    print("[✓] Phase 2 Corruption & Repair Flow completed successfully!")
    print("[i] Check comparison report in data/reports/comparison_report.md")
