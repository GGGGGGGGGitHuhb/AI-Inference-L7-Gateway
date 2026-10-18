import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "third_party/manifest.json").read_text())
for dependency in manifest["dependencies"]:
    for entry in dependency["files"]:
        actual = hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            raise AssertionError(entry["path"])
    assert (root / dependency["license"]).is_file()
print("All vendored file SHA256 digests match manifest")
