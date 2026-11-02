"""The gate never passes unless host, riscv and xtensa all succeeded, whatever the other results are."""
import contextlib
import io
import itertools
import pathlib
import subprocess
import sys

import yaml

import ci_gate

RESULTS = ("success", "failure", "cancelled", "skipped", "")
for combo in itertools.product(RESULTS, repeat=3):
    env = dict(zip(ci_gate.JOBS, combo))
    expected = 0 if combo == ("success",) * 3 else 1
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        code = ci_gate.main(env)
    assert code == expected, combo
print("Gate: all 125 result combinations passed")

# Through the real entry point, as the workflow runs it, with the environment the workflow wires to it.
script = str(pathlib.Path(__file__).with_name("ci_gate.py"))
def run(**env):
    return subprocess.run([sys.executable, script], env=env, capture_output=True, text=True).returncode
assert run(HOST="success", RISCV="success", XTENSA="success") == 0
assert run(HOST="success", RISCV="success", XTENSA="cancelled") == 1
assert run(HOST="success", RISCV="success") == 1
print("Gate entry point passed")

# The workflow feeds the gate from the three jobs, runs it even when they fail, and has no other mandatory job.
workflow = yaml.safe_load((pathlib.Path(__file__).resolve().parents[1] / "workflows" / "ci.yml").read_text())
gate = workflow["jobs"]["gate"]
assert sorted(gate["needs"]) == ["host", "riscv", "xtensa"], gate["needs"]
assert gate["if"] == "always()"
assert gate["steps"][-1]["env"] == {"HOST": "${{ needs.host.result }}", "RISCV": "${{ needs.riscv.result }}", "XTENSA": "${{ needs.xtensa.result }}"}
assert set(workflow["jobs"]) == {"host", "riscv", "xtensa", "gate"}
for name in ("host", "riscv", "xtensa"):
    assert "if" not in workflow["jobs"][name], f"{name} must not be conditional"
print("Workflow wiring passed")
