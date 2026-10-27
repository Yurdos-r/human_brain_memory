"""Package explicit source allowlists only. Never walk the user's original bot/data."""

import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"
PLUGIN = "astrbot_plugin_human_brain_memory"
FILES = ["__init__.py", "main.py", "metadata.yaml", "_conf_schema.json", "requirements.txt",
         "README.md", "README.en.md", "LICENSE", "CHANGELOG.md", "pyproject.toml", "MANIFEST.in", ".gitignore"]
TREES = ["human_brain_memory", "docs", "tests", "scripts", ".github"]


def package():
    paths = [ROOT / p for p in FILES]
    paths += [p for tree in TREES for p in (ROOT / tree).rglob("*")
              if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".py", ".md", ".json", ".yml"}]
    paths = sorted(set(paths))
    if any(not p.is_file() or p.is_symlink() for p in paths):
        raise ValueError("Missing or linked source file")
    manifest = {}
    # Detect credential assignments, not generic references to SDK configuration keys.
    secret = re.compile(r'(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})')
    for p in paths:
        data = p.read_bytes()
        if secret.search(data.decode("utf-8")):
            raise ValueError(f"Potential secret in {p.name}")
        manifest[p.relative_to(ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    archive = dist / f"{PLUGIN}-{VERSION}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            z.write(p, f"{PLUGIN}/{p.relative_to(ROOT).as_posix()}")
        z.writestr(f"{PLUGIN}/MANIFEST.sha256.json", json.dumps(manifest, indent=2, sort_keys=True))
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (dist / "SHA256SUMS.txt").write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")
    print(f"{archive}\n{len(paths)} source files; SHA256 {checksum}")
    return archive


if __name__ == "__main__":
    package()
