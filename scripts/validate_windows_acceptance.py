"""Validate a completed Windows acceptance record and optionally emit a safe copy."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from flcopilot.acceptance import AcceptanceError, load_record, write_public_record

def main(argv=None):
    p=argparse.ArgumentParser(description="Validate native Windows/FL acceptance evidence")
    p.add_argument("record",type=Path)
    p.add_argument("--public-out",type=Path)
    a=p.parse_args(argv)
    try:
        record=load_record(a.record)
        if a.public_out:
            write_public_record(record,a.public_out)
        print(json.dumps({"valid":True,"status":record["status"],
                          "required_passed":sum(record["tests"][k]=="pass" for k in record["tests"] if k!="model_vram_latency_underruns"),
                          "public_output":str(a.public_out) if a.public_out else None},indent=2))
        return 0
    except AcceptanceError as exc:
        print(json.dumps({"valid":False,"error":str(exc)},indent=2))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
