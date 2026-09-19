"""Compatibility entry point. Diagnostics now use the already-running app only."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flcopilot.cli import main
if __name__ == "__main__":
    raise SystemExit(main(["--diagnose", *sys.argv[1:]]))
