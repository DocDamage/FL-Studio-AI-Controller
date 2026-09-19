"""Validate native manual-export acceptance evidence and optionally emit a safe copy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flcopilot.render_acceptance import (
    REQUIRED_TESTS,
    RenderAcceptanceError,
    load_record,
    write_public_record,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate native Windows/FL manual-export acceptance evidence"
    )
    parser.add_argument("record", type=Path)
    parser.add_argument("--public-out", type=Path)
    args = parser.parse_args(argv)
    try:
        record = load_record(args.record)
        if args.public_out:
            write_public_record(record, args.public_out)
        print(json.dumps({
            "valid": True,
            "status": record["status"],
            "required_passed": sum(record["tests"][name] == "pass" for name in REQUIRED_TESTS),
            "required_total": len(REQUIRED_TESTS),
            "captures": len(record.get("captures", [])),
            "public_output": str(args.public_out) if args.public_out else None,
        }, indent=2))
        return 0
    except RenderAcceptanceError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
