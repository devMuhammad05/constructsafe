"""Clear generated data for a clean demo: the database, evidence images and outputs.

Uploaded videos (data/videos/), evaluation data (data/eval/) and model weights are kept.

    uv run python scripts/reset_demo.py        # show what would be deleted
    uv run python scripts/reset_demo.py --yes  # delete it
"""

from __future__ import annotations

import argparse
import shutil

from constructsafe.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="actually delete")
    args = parser.parse_args()

    config = load_config()
    targets = [config.database_path, config.evidence_dir, config.outputs_dir]
    for path in targets:
        if not path.exists():
            continue
        if not args.yes:
            print(f"would delete {path}")
        elif path.is_dir():
            shutil.rmtree(path)
            print(f"deleted {path}")
        else:
            path.unlink()
            print(f"deleted {path}")
    if not args.yes:
        print("dry run: pass --yes to delete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
