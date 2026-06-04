import os
from pathlib import Path

import pytest as pt

root = Path(__file__).parent / "fixtures" / "sample_project"
os.chdir(root)
config = pt.Config.fromdictargs({"pythonpath": ["."]}, ["--collect-only", "-q", "tests"])
session = pt.Session.from_config(config)
session.perform_collect()
print("count", len(session.items))
for i in session.items:
    print("nodeid", i.nodeid)
    print("path", getattr(i, "path", None))
    print("location", i.location)
    p = Path(str(getattr(i, "path", i.location[0]))).resolve()
    print("rel", p.relative_to(root.resolve()))
