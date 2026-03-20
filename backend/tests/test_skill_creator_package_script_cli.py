from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_package_skill_script_can_run_directly_as_cli(tmp_path: Path):
    skill_dir = tmp_path / "demo-skill"
    output_dir = tmp_path / "dist"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo skill\n---\n\n# Demo\n",
        encoding="utf-8",
    )

    script_path = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "public"
        / "skill-creator"
        / "scripts"
        / "package_skill.py"
    )

    result = subprocess.run(
        [sys.executable, str(script_path), str(skill_dir), str(output_dir)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert (output_dir / "demo-skill.skill").exists()
