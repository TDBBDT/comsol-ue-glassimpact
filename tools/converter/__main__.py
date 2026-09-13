import argparse
import json
from pathlib import Path

from .pipeline import convert


def main() -> int:
    parser = argparse.ArgumentParser(description="Project fixed reference FEM surface fields to UE textures.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--no-preview", action="store_true")
    args = parser.parse_args()
    try:
        result = convert(args.input, args.output, args.config, not args.no_preview)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Conversion failed: {exc}\n")
    print(json.dumps({"source_kind": result["source_kind"], "frames": result["frame_count"],
                      "resolution": result["texture_resolution"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
