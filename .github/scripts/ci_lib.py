"""Small runner shared by ci_host.py and ci_mcu.py: named groups, one failure summary, and a `--list` mode.

`--list` prints every command a script would run, with the environment it sets, and runs nothing: the
command inventory is tested (test_ci_inventory.py) so that no mandatory validation can be dropped by accident.
A validation that fails does not stop the others: all failures are reported together, then the script exits 1.
"""
import contextlib
import os
import shlex
import subprocess
import sys


class Runner:
    def __init__(self, list_only=False):
        self.list_only = list_only
        self.failures = []
        self.commands = []          # (group, environment, argv)
        self._group = ""

    @contextlib.contextmanager
    def group(self, name):
        self._group = name
        if self.list_only:
            print(f"## {name}")
        else:
            print(f"::group::{name}", flush=True)
        try:
            yield
        finally:
            if not self.list_only:
                print("::endgroup::", flush=True)

    def run(self, argv, env=None, must_fail_with=None, tee=None):
        """Run `argv` (with `env` added). `must_fail_with`: the command is expected to fail, and its output has to
        contain one of these texts (a refusal for the right reason, not any other breakage)."""
        env = env or {}
        self.commands.append((self._group, env, list(argv)))
        shown = " ".join([f"{k}={shlex.quote(v)}" for k, v in env.items()] + [shlex.quote(str(a)) for a in argv])
        if self.list_only:
            print("  " + shown)
            return True
        print("+ " + shown, flush=True)
        result = subprocess.run([str(a) for a in argv], env={**os.environ, **env}, capture_output=must_fail_with is not None or tee is not None,
                                text=True)
        output = (result.stdout or "") + (result.stderr or "")
        if tee is not None:
            sys.stdout.write(output)
            with open(tee, "a") as summary:
                summary.write(output)
        if must_fail_with is not None:
            ok = result.returncode != 0 and any(text in output for text in must_fail_with)
            if not ok:
                print(f"expected a refusal containing one of {must_fail_with}, got exit {result.returncode}:\n{output[-1500:]}", flush=True)
        else:
            ok = result.returncode == 0
        if not ok:
            self.failures.append(f"{self._group}: {shown}")
        return ok

    def finish(self):
        if self.list_only:
            return 0
        if self.failures:
            print("\nFAILED validations:", flush=True)
            for failure in self.failures:
                print(" - " + failure, flush=True)
            return 1
        print("\nAll validations passed.", flush=True)
        return 0
