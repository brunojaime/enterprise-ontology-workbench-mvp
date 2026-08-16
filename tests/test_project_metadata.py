from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).parents[1]
BACKLOG_PATH = REPOSITORY_ROOT / "enterprise_ontology_workbench_mvp_backlog.yaml"
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/ci.yaml"
RDF_WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/rdf-governance.yaml"
CODEOWNERS_PATH = REPOSITORY_ROOT / ".github/CODEOWNERS"
PR_TEMPLATE_PATH = REPOSITORY_ROOT / ".github/pull_request_template.md"
GITHUB_GOVERNANCE_PATH = REPOSITORY_ROOT / "docs/github-governance.md"
INTERNAL_COMPOSE_PATH = REPOSITORY_ROOT / "compose.internal.yaml"
OPERATIONS_PATH = REPOSITORY_ROOT / "docs/operations.md"
SCRIPT_NAMES = ("bootstrap", "dev", "test", "build", "validate")


def load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text())
    assert isinstance(document, dict)
    return document


def test_backlog_has_consistent_ids_dependencies_and_states() -> None:
    backlog = load_yaml(BACKLOG_PATH)
    plans = backlog["plans"]
    plan_by_id = {plan["id"]: plan for plan in plans}
    task_ids = [task["id"] for plan in plans for task in plan["tasks"]]
    allowed_states = set(backlog["task_status_values"])

    assert len(plan_by_id) == len(plans)
    assert len(task_ids) == len(set(task_ids))

    for plan in plans:
        assert set(plan["depends_on"]) <= plan_by_id.keys()
        assert plan["status"] in allowed_states
        assert all(task["status"] in allowed_states for task in plan["tasks"])
        if plan["status"] == "done":
            assert all(task["status"] == "done" for task in plan["tasks"])
        if plan["status"] in {"in_progress", "done"}:
            assert all(
                plan_by_id[dependency]["status"] == "done" for dependency in plan["depends_on"]
            )


def test_ci_runs_quality_type_checks_and_tests_for_pull_requests() -> None:
    workflow = load_yaml(WORKFLOW_PATH)
    all_run_steps = [
        step["run"] for job in workflow["jobs"].values() for step in job["steps"] if "run" in step
    ]
    commands = "\n".join(all_run_steps)

    assert "pull_request" in workflow["on"]
    assert "ruff check" in commands
    assert "mypy" in commands
    assert "pytest" in commands
    assert "generate_agent_files.py --check" in commands
    assert "evaluate_agent_tasks.py" in commands
    assert "pnpm lint" in commands
    assert "pnpm check" in commands
    assert "pnpm test" in commands
    assert workflow["jobs"]["python"]["name"] == "Python tests"
    assert workflow["jobs"]["cli-mcp"]["name"] == "CLI and MCP tests"
    assert workflow["jobs"]["frontend"]["name"] == "Frontend tests"
    assert "pytest apps/api/tests packages/ontology_core/tests tests" in commands
    assert "pytest packages/ontology_cli/tests packages/ontology_mcp/tests" in commands


def test_rdf_governance_workflow_fails_on_the_canonical_validation_pipeline() -> None:
    workflow = load_yaml(RDF_WORKFLOW_PATH)
    job = workflow["jobs"]["rdf-validation"]
    commands = [step["run"] for step in job["steps"] if "run" in step]

    assert "pull_request" in workflow["on"]
    assert workflow["permissions"] == {"contents": "read"}
    assert job["name"] == "RDF validation"
    assert "uv sync --frozen" in commands
    assert "uv run python scripts/validate_rdf.py" in commands


def test_agent_contract_has_a_stable_required_check_on_every_pull_request() -> None:
    workflow = load_yaml(RDF_WORKFLOW_PATH)
    job = workflow["jobs"]["agent-contract"]
    commands = [step["run"] for step in job["steps"] if "run" in step]

    assert workflow["on"]["pull_request"] == {}
    assert job["name"] == "Agent contract synchronization"
    assert "uv sync --frozen" in commands
    assert "uv run python scripts/generate_agent_files.py --check" in commands


def test_semantic_governance_job_uploads_artifact_and_pr_summary() -> None:
    workflow = load_yaml(RDF_WORKFLOW_PATH)
    job = workflow["jobs"]["semantic-review"]
    commands = "\n".join(step["run"] for step in job["steps"] if "run" in step)
    checkout = next(step for step in job["steps"] if step.get("uses") == "actions/checkout@v4")
    upload = next(step for step in job["steps"] if step.get("uses") == "actions/upload-artifact@v4")

    assert job["name"] == "Semantic governance report"
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.head.sha }}"
    assert "generate_pr_report.py" in commands
    assert '"$BASE_SHA"' in commands
    assert '"$HEAD_SHA"' in commands
    assert 'pr-summary.md >> "$GITHUB_STEP_SUMMARY"' in commands
    assert upload["if"] == "${{ always() }}"
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == 30


def test_codeowners_requires_review_for_governance_and_semantic_core() -> None:
    rules = {
        line.split()[0]: tuple(line.split()[1:])
        for line in CODEOWNERS_PATH.read_text().splitlines()
        if line and not line.startswith("#")
    }

    assert rules["/knowledge/"]
    assert rules["/config/"]
    assert rules["/agent_contract/"]
    assert rules["/packages/ontology_core/"]
    assert rules["/.github/workflows/"]
    assert all(owner.startswith("@") for owners in rules.values() for owner in owners)


def test_ontology_pull_request_template_requests_governance_evidence() -> None:
    template = PR_TEMPLATE_PATH.read_text().lower()

    for required in (
        "motivo",
        "evidencia",
        "impacto",
        "preguntas de competencia",
        "búsqueda previa",
        "diff semántico",
        "términos deprecados",
    ):
        assert required in template
    assert "proposal/*" in template
    assert "search_id" in template


def test_main_ruleset_documentation_names_every_required_check_and_protection() -> None:
    documentation = GITHUB_GOVERNANCE_PATH.read_text()

    for check in (
        "RDF validation",
        "Semantic governance report",
        "Agent contract synchronization",
        "Python tests",
        "CLI and MCP tests",
        "Frontend tests",
    ):
        assert f"`{check}`" in documentation
    for protection in ("pull requests", "CODEOWNERS", "force-push", "eliminación de `main`"):
        assert protection in documentation
    assert "al menos una aprobación" in documentation
    assert "resolución de todas las conversaciones" in documentation


def provisioned_tools_before_each_run(job: dict[str, Any]) -> list[tuple[str, set[str]]]:
    provisioned: set[str] = set()
    runs: list[tuple[str, set[str]]] = []
    for step in job["steps"]:
        action = step.get("uses", "")
        if action.startswith("actions/setup-python@"):
            provisioned.add("python")
        elif action.startswith("astral-sh/setup-uv@"):
            provisioned.add("uv")
        elif action.startswith("pnpm/action-setup@"):
            provisioned.add("pnpm")
        elif action.startswith("actions/setup-node@"):
            provisioned.add("node")
        if "run" in step:
            runs.append((step["run"], provisioned.copy()))
    return runs


def required_tools(command: str) -> set[str]:
    requirements: set[str] = set()
    if command.startswith("uv ") or " uv " in command:
        requirements.update({"python", "uv"})
    if command.startswith("pnpm ") or " pnpm " in command:
        requirements.update({"node", "pnpm"})
    if "./scripts/bootstrap.sh" in command:
        requirements.update({"python", "uv", "node", "pnpm"})
    return requirements


def test_ci_provisions_every_tool_before_it_is_used() -> None:
    workflow = load_yaml(WORKFLOW_PATH)

    for job_name, job in workflow["jobs"].items():
        for command, provisioned in provisioned_tools_before_each_run(job):
            missing = required_tools(command) - provisioned
            assert not missing, f"{job_name}: {command!r} lacks {sorted(missing)}"


def test_ci_jobs_install_only_their_locked_workspace() -> None:
    workflow = load_yaml(WORKFLOW_PATH)
    python_commands = [step["run"] for step in workflow["jobs"]["python"]["steps"] if "run" in step]
    frontend_commands = [
        step["run"] for step in workflow["jobs"]["frontend"]["steps"] if "run" in step
    ]
    cli_mcp_commands = [
        step["run"] for step in workflow["jobs"]["cli-mcp"]["steps"] if "run" in step
    ]

    assert "uv sync --frozen" in python_commands
    assert "uv sync --frozen" in frontend_commands
    assert "uv sync --frozen" in cli_mcp_commands
    assert "pnpm install --frozen-lockfile" in frontend_commands
    assert "uv run python scripts/generate_api_client.py --check" in frontend_commands
    assert "./scripts/bootstrap.sh" not in frontend_commands


def test_full_bootstrap_requires_both_toolchains() -> None:
    frontend_only_job = {
        "steps": [
            {"uses": "pnpm/action-setup@v4"},
            {"uses": "actions/setup-node@v4"},
            {"run": "./scripts/bootstrap.sh"},
        ]
    }
    command, provisioned = provisioned_tools_before_each_run(frontend_only_job)[0]

    assert required_tools(command) - provisioned == {"python", "uv"}


def test_bash_and_powershell_entry_points_have_matching_names() -> None:
    for script_name in SCRIPT_NAMES:
        assert (REPOSITORY_ROOT / "scripts" / f"{script_name}.sh").is_file()
        assert (REPOSITORY_ROOT / "scripts" / f"{script_name}.ps1").is_file()


def test_documentation_bootstraps_a_clean_checkout() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text()
    development = (REPOSITORY_ROOT / "docs/development.md").read_text()

    assert "./scripts/bootstrap.sh" in readme
    assert "./scripts/bootstrap.ps1" in readme
    assert "uv sync --frozen" in development
    assert "pnpm@9.15.5 install --frozen-lockfile" in development


def test_container_context_excludes_local_environments_but_keeps_example() -> None:
    patterns = (REPOSITORY_ROOT / ".dockerignore").read_text().splitlines()

    assert ".env" in patterns
    assert ".env.*" in patterns
    assert "!.env.example" in patterns
    assert "!.env.internal.example" in patterns


def test_api_and_web_images_run_as_unprivileged_users() -> None:
    api = (REPOSITORY_ROOT / "apps/api/Containerfile").read_text()
    web = (REPOSITORY_ROOT / "apps/web/Containerfile").read_text()

    assert "USER 10001:10001" in api
    assert 'CMD ["python", "-m", "enterprise_ontology_api"]' in api
    assert "USER node" in web
    assert "EOW_API_UPSTREAM_URL=http://api:8000" in web
    assert "ORIGIN=http://localhost:3000" in web


def test_internal_compose_confines_repository_and_runtime() -> None:
    compose = load_yaml(INTERNAL_COMPOSE_PATH)
    api = compose["services"]["api"]
    web = compose["services"]["web"]
    mount = api["volumes"][0]
    environment = (REPOSITORY_ROOT / ".env.internal.example").read_text()

    assert api["read_only"] is True
    assert web["read_only"] is True
    assert api["cap_drop"] == ["ALL"] and web["cap_drop"] == ["ALL"]
    assert "privileged" not in api and "privileged" not in web
    assert mount["target"] == "/repository"
    assert mount["source"].startswith("${EOW_REPOSITORY_PATH:?")
    assert mount["read_only"] == "${EOW_REPOSITORY_READ_ONLY:-true}"
    assert api["environment"]["EOW_WRITE_ENABLED"] == "${EOW_WRITE_ENABLED:-false}"
    assert "EOW_REPOSITORY_READ_ONLY=true" in environment
    assert "EOW_WRITE_ENABLED=false" in environment
    assert "/ready" in " ".join(api["healthcheck"]["test"])
    assert web["environment"]["ORIGIN"] == "${EOW_WEB_ORIGIN:-http://localhost:3000}"


def test_operations_document_backup_update_and_final_smoke() -> None:
    documentation = OPERATIONS_PATH.read_text()
    smoke = (REPOSITORY_ROOT / "scripts/smoke_package.py").read_text()
    mcp_package = (REPOSITORY_ROOT / "packages/ontology_mcp/pyproject.toml").read_text()

    for requirement in (
        "remoto Git protegido",
        "Un cambio sin commit ni push no está respaldado",
        "Recuperación desde pérdida del host",
        "agent_contract/manifest.yaml",
        "migración ontológica",
        "rollback",
        "scripts/smoke_package.py",
        "GET /metrics",
        "500 inesperados",
    ):
        assert requirement in documentation
    for executable in ("ontology", "ontology-mcp-smoke"):
        assert executable in smoke
    for metric in ('"load"', '"validation"', '"query"'):
        assert metric in smoke
    assert 'ontology-mcp-smoke = "ontology_mcp.smoke:main"' in mcp_package


def test_compose_exposes_the_real_git_checkout_for_controlled_p07_writes() -> None:
    compose = load_yaml(REPOSITORY_ROOT / "compose.yaml")
    api = compose["services"]["api"]
    mount = api["volumes"][0]
    environment_example = (REPOSITORY_ROOT / ".env.example").read_text()
    development = (REPOSITORY_ROOT / "docs/development.md").read_text()

    assert mount == {
        "type": "bind",
        "source": ".",
        "target": "/repository",
        "read_only": False,
    }
    assert api["environment"]["EOW_REPOSITORY_ROOT"] == "/repository"
    assert api["environment"]["EOW_KNOWLEDGE_ROOT"] == "/repository/knowledge"
    assert api["environment"]["GIT_CONFIG_VALUE_0"] == "/repository"
    assert api["environment"]["EOW_WRITE_ENABLED"] == "true"
    assert "EOW_WRITE_ENABLED=false" in environment_example
    assert "overrides that value to true" in environment_example
    assert "read/write at /repository" in environment_example
    assert "read-only at /repository" not in environment_example
    assert "modo lectura/escritura" in development
    assert "EOW_WRITE_ENABLED=true" in development
    assert "fuera de Compose las mutaciones quedan\ndeshabilitadas por defecto" in development
    assert ".git" in (REPOSITORY_ROOT / ".dockerignore").read_text().splitlines()
    assert (
        "apt-get install --yes --no-install-recommends git"
        in (REPOSITORY_ROOT / "apps/api/Containerfile").read_text()
    )


def test_workspace_page_reports_the_operational_rdf_snapshot() -> None:
    page = (REPOSITORY_ROOT / "apps" / "web" / "src" / "routes" / "+page.svelte").read_text()

    assert "Dashboard del conocimiento" in page
    assert "apiGet<Workspace>('/api/workspace')" in page
    assert "Validación conforme" in page
    assert "Módulos cargados" in page
    assert "exposición HTTP y la navegación visual se incorporarán" not in page
    assert "incorporar el repositorio RDF en el próximo" not in page


def test_agent_contract_is_canonical_and_generated_adapters_are_synchronized() -> None:
    from ontology_core import AgentContractService

    service = AgentContractService(REPOSITORY_ROOT)
    status = service.status()

    assert status.version == "1.0.0"
    assert status.synchronized
    assert status.rules == (
        "principles",
        "modeling_decision_tree",
        "change_protocol",
        "prohibited_patterns",
    )
    assert status.skills == ("ontology_discover", "ontology_author", "ontology_review")
    assert (REPOSITORY_ROOT / "AGENTS.md").read_text() == (
        REPOSITORY_ROOT / "CLAUDE.md"
    ).read_text().replace("Claude Code", "Codex")
