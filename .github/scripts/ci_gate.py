#!/usr/bin/env python3
"""Final gate of the CI: passes only if every mandatory job finished with `success`.

Fail closed: a skipped, cancelled, failed or missing result is a failure. Nothing is optional, so there is no
"not selected" case to tolerate: every event (pull request, push, nightly, manual) runs the three families.

  HOST=success RISCV=success XTENSA=success ci_gate.py
"""
import os
import sys

JOBS = ("HOST", "RISCV", "XTENSA")


def main(env=os.environ):
    bad = [f"{job.lower()}: {env.get(job) or 'missing'}" for job in JOBS if env.get(job) != "success"]
    if bad:
        print("CI gate refused: " + ", ".join(bad), file=sys.stderr)
        return 1
    print("CI gate: host, riscv and xtensa succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
