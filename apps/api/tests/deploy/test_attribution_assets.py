"""Exercise attribution with the production release layout and a separate data volume."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_release_can_read_bundled_attribution_assets(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    release = tmp_path / "releases" / "candidate"
    api = release / "api"
    data = tmp_path / "shared" / "data"
    manifest = Path("deploy/attribution-assets.list")
    for resource in [str(manifest), *(ROOT / manifest).read_text().splitlines()]:
        destination = checkout / resource
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / resource, destination)
    node = shutil.which("node")
    assert node, "Node is required for the release build"
    subprocess.run(  # noqa: S603 - invoke the repository build script in the temporary checkout.
        [node, str(ROOT / "scripts/stage-attribution-assets.mjs")], cwd=checkout, check=True
    )
    shutil.copytree(
        ROOT / "apps/api/app",
        checkout / "apps/api/app",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # The deploy transport copies the api directory alone to <release>/api.
    shutil.copytree(checkout / "apps/api", api)
    shutil.rmtree(checkout)

    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("HE_") and key != "PYTHONPATH"
    }
    env.update(
        HE_DATA_DIR=str(data),
        HE_PRODUCTION="true",
        HE_DB_DIALECT="sqlite",
        HE_JWT_SECRET=os.urandom(32).hex(),
    )
    script = """
import asyncio
import io
import zipfile
from pathlib import Path

from app.cli import main
from app.config import Settings
from app.db.crud.attribution_skill_packages import AttributionSkillPackageRepository
from app.db.factory import create_database
from app.service.evolution.attribution_skill_packages import AttributionSkillPackageService

settings = Settings()
assert settings.attribution_package_dir == settings.data_dir / 'attribute'
resources = Path.cwd() / 'release-assets'
assert settings.attribution_default_skill_path == resources / 'attribute-badcases/SKILL.md'
assert settings.attribution_golden_set_path == resources / 'fixtures/attribution-golden/cases.json'
packages = AttributionSkillPackageService(
    AttributionSkillPackageRepository(create_database(settings)),
    settings.attribution_package_dir, settings.attribution_default_skill_path,
)
name, archive = asyncio.run(packages.download('workspace', 'default-attribute-badcases'))
with zipfile.ZipFile(io.BytesIO(archive)) as package:
    assert package.read('attribute-badcases/SKILL.md')
    assert package.read('attribute-badcases/make_probe_report.py')
assert main(['attribution-eval', '--engine', 'rule-v1']) == 0
"""
    result = subprocess.run(  # noqa: S603 - current Python runs a fixed smoke script.
        [sys.executable, "-c", script], cwd=api, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr or result.stdout
