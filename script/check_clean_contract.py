from __future__ import annotations

import json

from core.clean_contract import audit_clean_contract
from core.config import load_settings


def main() -> int:
    settings = load_settings()
    report = audit_clean_contract(settings)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
