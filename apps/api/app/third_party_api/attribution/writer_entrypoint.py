"""Per-attempt CLI shim. Forward the Skill's arguments to its pinned platform writer."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Record the successful writer output for the parent to validate and regenerate."""
    # This file is copied to skills/<name>/make_probe_report.py in the attempt's
    # neutral layout. The attempt root is the ancestor that holds .platform, so
    # the shim never depends on one staging depth.
    staged = Path(__file__).resolve()
    work = next((p for p in staged.parents if (p / ".platform").is_dir()), staged.parents[-1])
    writer = work / ".platform" / "make_probe_report.py"
    result = subprocess.run(  # noqa: S603 - fixed interpreter and pinned script
        [sys.executable, "-I", str(writer), *sys.argv[1:]],
        stdout=subprocess.PIPE,
        check=False,
        text=True,
    )
    if result.returncode:
        return result.returncode
    path = Path(result.stdout.strip()).resolve()
    if path.name != "probe_report.json" or not path.is_relative_to(work):
        return 2
    if not path.is_file() or path.stat().st_size > 2_000_000:
        return 2
    receipt = {
        "path": str(path.relative_to(work)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (work / ".platform" / "receipt.json").write_text(json.dumps(receipt))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
