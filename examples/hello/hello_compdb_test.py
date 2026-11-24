"""Check the portable compilation database produced by the Meson fixture."""

import json
from pathlib import Path
import sys


entries = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if len(entries) != 1:
    raise SystemExit(f"expected one compilation entry, got {len(entries)}")

entry = entries[0]
source = Path(entry["file"])
if source.is_absolute() or source.name != "hello.c" or entry["directory"] != ".":
    raise SystemExit(f"unexpected compilation source or directory: {entry}")
if not entry.get("arguments") or entry["file"] not in entry["arguments"]:
    raise SystemExit("compilation arguments omit the hello.c source")
