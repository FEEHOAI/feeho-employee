from __future__ import annotations

import argparse
from pathlib import Path

from .runtime import hook_main


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m feeho_employee.cc_hook")
    parser.add_argument("--package", default=".")
    args = parser.parse_args()
    return hook_main(Path(args.package).expanduser().resolve())


if __name__ == "__main__":
    raise SystemExit(main())
