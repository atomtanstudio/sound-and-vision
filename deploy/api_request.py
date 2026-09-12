"""Operator helper: credentials are read from a file, never from CLI arguments."""

import argparse, json, urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("path")
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--json", type=Path)
parser.add_argument("--method")
args = parser.parse_args()
request = urllib.request.Request(
    "http://127.0.0.1:5191" + args.path,
    data=args.json.read_bytes() if args.json else None,
    headers={
        "Authorization": "Bearer " + (args.root / "service.token").read_text().strip(),
        "Content-Type": "application/json",
    },
    method=args.method,
)
with urllib.request.urlopen(request, timeout=30) as response:
    print(response.read().decode())
