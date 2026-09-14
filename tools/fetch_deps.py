"""Fetch the pinned Android Frida server for a developer build (not at app startup)."""

import hashlib
import json
import ssl
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
m = json.loads((ROOT / "resources/frida.json").read_text(encoding="utf-8"))
p = ROOT / "resources" / m["file"]
if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != m["archive_sha256"]:
    with urllib.request.urlopen(
        m["url"],
        timeout=120,
        context=ssl.create_default_context(
            cafile="/etc/ssl/cert.pem" if Path("/etc/ssl/cert.pem").is_file() else None
        ),
    ) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != m["archive_sha256"]:
        raise RuntimeError("Downloaded Frida checksum mismatch")
    tmp = p.with_suffix(".download")
    tmp.write_bytes(data)
    tmp.replace(p)
print("Frida dependency verified:", m["version"])
