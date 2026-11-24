"""Static contract for the deployment provisioning path.

The PR CI ``deploy-contract`` job proves the runtime contract on a clean Ubuntu
host; these tests run everywhere (including the normal API suite) so a change
that drops a provisioning source fails before merge even without the container
job. They intentionally assert the wiring rather than re-implement it.
"""

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PREREQUISITES = ROOT / "deploy/attribution-runtime-prerequisites.list"
BOOTSTRAP = ROOT / "deploy/bootstrap-server.sh"
CLOUD_INIT = ROOT / "deploy/cloud-init.yaml"
PROVISION = ROOT / "deploy/provision-bubblewrap.sh"
RELEASE = ROOT / "deploy/release.sh"
CI = ROOT / ".github/workflows/ci.yml"
PROVISION_WORKFLOW = ROOT / ".github/workflows/provision.yml"
CONTRACT_SCRIPT = ROOT / "apps/api/tests/deploy/verify_provisioning_contract.sh"


def runtime_packages() -> list[str]:
    """Return the canonical runtime prerequisite package names."""
    packages = []
    for raw in PREREQUISITES.read_text(encoding="utf-8").splitlines():
        entry = raw.split("#", 1)[0].strip()
        if entry:
            packages.append(entry)
    return packages


def job_block(workflow: str, job: str) -> str:
    """Return the YAML text of one workflow job, up to the next top-level key."""
    match = re.search(rf"^  {re.escape(job)}:\n", workflow, re.MULTILINE)
    assert match, f"missing job {job}"
    rest = workflow[match.end() :]
    next_job = re.search(r"^  [a-z][a-z0-9_-]*:\n", rest, re.MULTILINE)
    return rest[: next_job.start()] if next_job else rest


def ci_ok_needs(workflow: str) -> list[str]:
    """Return the names listed in the ``ci-ok`` job's ``needs`` block."""
    block = job_block(workflow, "ci-ok")
    needs_start = block.find("needs:")
    assert needs_start >= 0, "ci-ok has no needs"
    opening = block.find("[", needs_start)
    closing = block.find("]", opening)
    assert opening >= 0 and closing > opening, "ci-ok needs is not a list"
    return [item.strip() for item in block[opening + 1 : closing].split(",") if item.strip()]


def test_runtime_prerequisite_list_is_the_single_source() -> None:
    packages = runtime_packages()
    assert packages, "attribution-runtime-prerequisites.list must list at least one package"
    assert "bubblewrap" in packages, "bubblewrap is the attribution runtime prerequisite"


def test_bootstrap_installs_every_runtime_prerequisite() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "attribution-runtime-prerequisites.list" in text, "bootstrap must read the shared list"
    assert '"${RUNTIME_PACKAGES[@]}"' in text, "bootstrap must install the shared list"
    install_line = next(line for line in text.splitlines() if line.startswith("apt-get install"))
    assert "bubblewrap" not in install_line.replace("${RUNTIME_PACKAGES[@]}", ""), (
        "bubblewrap must come from the shared list, not a second hard-coded copy"
    )


def test_cloud_init_mirrors_every_runtime_prerequisite() -> None:
    text = CLOUD_INIT.read_text(encoding="utf-8")
    section = text.split("packages:", 1)[1].split("runcmd:", 1)[0]
    packages = {
        line.strip().removeprefix("-").strip()
        for line in section.splitlines()
        if line.strip().startswith("-")
    }
    missing = sorted(set(runtime_packages()) - packages)
    assert not missing, f"cloud-init is missing runtime prerequisites: {missing}"


def test_provision_script_installs_the_attribution_prerequisite() -> None:
    text = PROVISION.read_text(encoding="utf-8")
    for package in runtime_packages():
        assert f"install -y --no-install-recommends {package}" in text, (
            f"provision script must install {package}"
        )
    assert "apt-get" in text and "install" in text


def test_release_runs_preflight_before_switching_current() -> None:
    lines = RELEASE.read_text(encoding="utf-8").splitlines()
    preflight = next(
        index
        for index, line in enumerate(lines)
        if "-m app.third_party_api.ai_agent.preflight" in line
    )
    switch = next(
        index for index, line in enumerate(lines) if 'ln -sfn "$RELEASE" "$CURRENT.tmp"' in line
    )
    assert preflight < switch, "preflight must run before the current symlink switches"
    assert any("尚未执行迁移或切换 current" in line for line in lines[preflight : preflight + 2])


def test_ci_runs_the_provisioning_contract_on_a_clean_ubuntu_host() -> None:
    text = CI.read_text(encoding="utf-8")
    block = job_block(text, "deploy-contract")
    assert "runs-on: ubuntu-latest" in block or "runs-on: ubuntu-24.04" in block
    assert "container:" in block, "deploy-contract must not trust a preinstalled runner"
    assert "image: ubuntu:24.04" in block
    assert "bash apps/api/tests/deploy/verify_provisioning_contract.sh" in block
    assert "pytest apps/api/tests/deploy/test_provisioning_contract.py" in block


def test_ci_ok_requires_the_provisioning_contract() -> None:
    needs = ci_ok_needs(CI.read_text(encoding="utf-8"))
    assert "deploy-contract" in needs, "ci-ok must aggregate deploy-contract"


def test_provision_workflow_reuses_the_same_script() -> None:
    text = PROVISION_WORKFLOW.read_text(encoding="utf-8")
    assert "deploy/provision-bubblewrap.sh" in text, (
        "Provision workflow and PR CI must share the provisioning script"
    )


def test_contract_script_covers_negative_positive_and_real_preflight() -> None:
    assert CONTRACT_SCRIPT.is_file(), "runtime contract script is missing"
    text = CONTRACT_SCRIPT.read_text(encoding="utf-8")
    assert "--check" in text and "--install" in text
    assert "ATTRIBUTION_BWRAP_MISSING" in text
    assert "state=ready" in text
    assert "app.third_party_api.ai_agent.preflight" in text
    assert "ready=True" in text
    assert "runuser" in text and "harness" in text
    assert "bwrap --unshare-all --share-net --die-with-parent --ro-bind / / -- /bin/true" in text


def test_contract_script_resolves_the_repository_root() -> None:
    """The script sits four levels below the repository root."""
    bash = shutil.which("bash")
    assert bash, "bash is required"
    resolved = subprocess.run(  # noqa: S603 - fixed local bash expression, no user input.
        [
            bash,
            "-c",
            'cd "$(dirname "$1")/../../../.." && pwd',
            "_",
            str(CONTRACT_SCRIPT),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert Path(resolved) == ROOT
