"""Call the ck CLI without a shell (safe for long, multi-line, quoted arguments on Windows)."""
import json
import os
import shutil
import subprocess
from pathlib import Path


def _cli():
    appdata = os.environ.get("APPDATA")
    if appdata:
        entry = Path(appdata) / "npm" / "node_modules" / "@callkaro-official" / "cli" / "dist" / "index.js"
        if entry.exists():
            return [shutil.which("node") or "node", str(entry)]
    return [shutil.which("ck") or "ck"]


def ck(*args, json_out=False, check=True):
    cmd = _cli() + [str(a) for a in args]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise RuntimeError("ck %s failed (%s):\n%s\n%s" % (" ".join(map(str, args[:3])), p.returncode, p.stdout[-2000:], p.stderr[-2000:]))
    if json_out:
        return json.loads(p.stdout)
    return p.stdout
