"""Copy the claude.ai Singapore dashboard's page into site/sg/.

  python3 site/sync_from_dashboard.py DIR

DIR holds the dashboard's files/ documents saved as JSON (ArtifactData list, collection "files", out_dir):
index.html.json, cpi.js.json, export.js.json. The page body goes between site/sg/wrapper_head.html and
wrapper_tail.html (page head, theme tokens, d3, shim.js).
"""
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
here = Path(__file__).resolve().parent / "sg"
text = lambda n: json.loads((src / f"{n}.json").read_text())["text"]  # noqa: E731
page = text("index.html").replace('<script src="cpi.js"></script>\n<script src="export.js"></script>\n', "")
(here / "index.html").write_text((here / "wrapper_head.html").read_text() + page + (here / "wrapper_tail.html").read_text())
for n in ("cpi.js", "export.js"):
    (here / n).write_text(text(n))
print("synced", ", ".join(["index.html", "cpi.js", "export.js"]))
