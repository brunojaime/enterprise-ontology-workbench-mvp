import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parents[1]
SHELL_LIBRARY = REPOSITORY_ROOT / "scripts/lib.sh"
POWERSHELL_LIBRARY = REPOSITORY_ROOT / "scripts/lib.ps1"


def make_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run_bash(
    function_name: str,
    tool_directory: Path,
    *arguments: str,
    **environment: str,
) -> subprocess.CompletedProcess[str]:
    process_environment = os.environ | environment
    process_environment["PATH"] = f"{tool_directory}:{process_environment['PATH']}"
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; shift; "$@"',
            "bash",
            str(SHELL_LIBRARY),
            function_name,
            *arguments,
        ],
        check=False,
        capture_output=True,
        env=process_environment,
        text=True,
    )


def test_bash_compose_falls_back_from_incapable_docker_to_podman(tmp_path: Path) -> None:
    invocation_log = tmp_path / "compose.log"
    make_executable(
        tmp_path / "docker",
        '#!/bin/sh\nif [ "$1 $2" = "compose version" ]; then exit 1; fi\nexit 99\n',
    )
    make_executable(
        tmp_path / "podman",
        "#!/bin/sh\n"
        'if [ "$1 $2" = "compose version" ]; then exit 0; fi\n'
        'printf "%s\\n" "$*" > "$COMPOSE_LOG"\n',
    )

    result = run_bash(
        "run_compose",
        tmp_path,
        "up",
        "--build",
        COMPOSE_LOG=str(invocation_log),
    )

    assert result.returncode == 0, result.stderr
    assert invocation_log.read_text().strip() == "compose up --build"


@pytest.mark.parametrize("exit_code", [2, 23])
def test_bash_compose_preserves_provider_exit_code(tmp_path: Path, exit_code: int) -> None:
    make_executable(
        tmp_path / "docker",
        f'#!/bin/sh\nif [ "$1 $2" = "compose version" ]; then exit 0; fi\nexit {exit_code}\n',
    )

    result = run_bash("run_compose", tmp_path, "config")

    assert result.returncode == exit_code


def test_bash_bootstrap_uses_both_frozen_lockfiles(tmp_path: Path) -> None:
    invocation_log = tmp_path / "bootstrap.log"
    logger = '#!/bin/sh\nprintf "%s %s\\n" "$(basename "$0")" "$*" >> "$BOOTSTRAP_LOG"\n'
    make_executable(tmp_path / "uv", logger)
    make_executable(tmp_path / "pnpm", logger)

    result = run_bash("bootstrap_workspace", tmp_path, BOOTSTRAP_LOG=str(invocation_log))

    assert result.returncode == 0, result.stderr
    assert invocation_log.read_text().splitlines() == [
        "uv sync --frozen",
        "pnpm install --frozen-lockfile",
    ]


def test_powershell_compose_source_probes_and_falls_back_before_execution() -> None:
    source = POWERSHELL_LIBRARY.read_text()

    docker_probe = source.index('Test-ComposeProvider -Name "docker"')
    podman_probe = source.index('Test-ComposeProvider -Name "podman"')
    assert "& $Name compose version *> $null" in source
    assert docker_probe < podman_probe
    assert "& docker compose @Arguments\n        Assert-LastExitCode" in source
    assert "& podman compose @Arguments\n        Assert-LastExitCode" in source


def test_workflow_entrypoints_bootstrap_before_local_commands() -> None:
    for script_name in ("test", "validate", "build"):
        bash_source = (REPOSITORY_ROOT / "scripts" / f"{script_name}.sh").read_text()
        powershell_source = (REPOSITORY_ROOT / "scripts" / f"{script_name}.ps1").read_text()

        assert bash_source.index("bootstrap_workspace") < bash_source.index("uv ")
        assert powershell_source.index("Initialize-Workspace") < powershell_source.index("& uv ")


def test_validation_gates_are_shared_by_bash_and_powershell() -> None:
    bash_source = (REPOSITORY_ROOT / "scripts" / "validate.sh").read_text()
    powershell_source = (REPOSITORY_ROOT / "scripts" / "validate.ps1").read_text()

    shared_commands = (
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy apps/api/src packages/ontology_core/src "
        "packages/ontology_cli/src packages/ontology_mcp/src",
        "uv run python scripts/validate_rdf.py",
        "uv run python scripts/generate_agent_files.py --check",
        "uv run python scripts/evaluate_agent_tasks.py",
        "uv run python scripts/check_mcp_clients.py",
        "uv run python scripts/generate_api_client.py --check",
    )
    for command in shared_commands:
        assert command in bash_source
        assert f"& {command}\nAssert-LastExitCode" in powershell_source
    assert "run_pnpm lint" in bash_source
    assert "run_pnpm check" in bash_source
    assert "Invoke-Pnpm lint" in powershell_source
    assert "Invoke-Pnpm check" in powershell_source

    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / "validate_rdf.py")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "conforms": True,
        "counts": {"error": 0, "info": 0, "warning": 0},
        "issues": [],
    }
