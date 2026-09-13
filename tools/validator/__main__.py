import argparse
import json
from pathlib import Path
from converter.readers import load_series
from .processed import validate_processed

parser = argparse.ArgumentParser(description="Validate raw fixed-reference glass surface exports, including damage irreversibility.")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--input", type=Path)
group.add_argument("--processed", type=Path)
args = parser.parse_args()
try:
    if args.processed:
        result = validate_processed(args.processed)
    else:
        series = load_series(args.input)
        result = {"valid": True, "source_kind": series.source["source_kind"], "frames": len(series.times),
                  "nodes": len(series.node_ids), "duration_seconds": float(series.times[-1]), "physics_validated": False}
except (OSError, ValueError) as exc:
    parser.exit(2, f"Validation failed: {exc}\n")
print(json.dumps(result))
