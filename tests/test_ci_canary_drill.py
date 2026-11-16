"""Contract for the canary alert path in ci.yml.

``report-canary-failure`` only runs after ``refresh-tier1`` fails on main, so a
healthy canary never exercises it. The ``canary-drill`` dispatch makes
``refresh-tier1`` fail on purpose, which is the only way to run the alert job
for real without waiting for an upstream docs outage.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CI = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def _job(name: str) -> str:
    """The `name` job of ci.yml, up to the next job (or the end of the file)."""
    lines = CI.splitlines()
    start = lines.index(f"  {name}:")
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        if line.startswith("  ") and line.endswith(":") and not line.startswith("   "):
            return "\n".join(lines[start:offset])
    return "\n".join(lines[start:])


def _job_if(job: str) -> str:
    return next(
        line.strip() for line in job.splitlines() if line.startswith("    if: ")
    )


def test_canary_drill_is_a_dispatch_choice():
    job_input = CI[CI.index("      job:") : CI.index("permissions:")]

    assert "          - canary-drill" in job_input
    assert "canary-drill" in job_input.split("options:")[0], (
        "description must explain the drill"
    )


def test_drill_fails_refresh_tier1_before_any_real_work():
    refresh = _job("refresh-tier1")

    assert "inputs.job == 'canary-drill'" in _job_if(refresh)
    drill = refresh.index("name: Fail on purpose for a canary drill")
    assert (
        "if: inputs.job == 'canary-drill'"
        in refresh[drill : refresh.index("run:", drill)]
    )
    assert "exit 1" in refresh[drill : refresh.index("- name:", drill + 1)]
    assert drill < refresh.index("name: Checkout code")


def test_alert_job_runs_for_a_failed_drill_on_main_only():
    gate = _job_if(_job("report-canary-failure"))

    assert gate.startswith("if: failure() && ")
    assert "github.event_name == 'workflow_dispatch'" in gate
    assert "inputs.job == 'refresh-tier1'" in gate
    assert "inputs.job == 'canary-drill'" in gate
    assert "github.ref == 'refs/heads/main'" in gate


def test_drill_issue_is_marked_as_a_drill():
    alert = _job("report-canary-failure")

    assert "DRILL: ${{ inputs.job == 'canary-drill' }}" in alert
    assert 'if [ "$DRILL" = "true" ]' in alert
    assert "Tier 1 canary drill on" in alert
