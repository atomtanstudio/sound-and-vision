"""Run the production art-direction pipeline against an explicit song brief.

Intended for isolated acceptance tests; does not write to the live song database.
The provider root must be an existing, connected Sound/Vision installation.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.providers import Providers
from backend.song_reactive import create_artwork


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-root", type=Path, required=True)
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path, action="append", default=[],
                        help="Explicit artwork revision reference; always use a fresh output version.")
    args = parser.parse_args()
    data = json.loads(args.brief.read_text())
    provider = Providers(args.provider_root)
    try:
        result = await create_artwork(provider, data["song"], data.get("aspect", "16:9"), args.output,
            lambda phase: print(json.dumps({"phase": phase}), flush=True),
            reference_images=[str(p.resolve()) for p in args.reference])
        print(json.dumps({"ready": True, "concept": result["concept"], "effects": [s["effect"] for s in result["surfaces"]], "output": str(args.output)}), flush=True)
    finally:
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
