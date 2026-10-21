"""Fetch the public, licensed font and verify its recorded checksum."""
from pathlib import Path
import hashlib
import json
from urllib.request import urlopen

root = Path(__file__).resolve().parent / "fonts"
data = json.loads((root / "font-source.json").read_text())
for entry in data["files"]:
    path = root / entry["file"]
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]:
        continue
    with urlopen(entry["source"], timeout=60) as response:
        body = response.read()
    if hashlib.sha256(body).hexdigest() != entry["sha256"]:
        raise SystemExit("Font checksum mismatch: " + entry["file"])
    path.write_bytes(body)
print("Licensed Korean font checksum verified")
