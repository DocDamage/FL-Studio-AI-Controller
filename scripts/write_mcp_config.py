"""Print a ready-to-paste MCP client block using this environment; no client files are changed."""
import json
import sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
from flcopilot.cli import default_workspace
print(json.dumps({"mcpServers":{"fl-studio-copilot":{"command":sys.executable,
    "args":["-m","flcopilot","--mcp","--workspace",str(default_workspace())],"cwd":str(root)}}},indent=2))
