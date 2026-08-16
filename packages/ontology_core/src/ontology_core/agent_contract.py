"""Canonical, deterministic agent contract and generated adapters."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from string import Formatter
from typing import Any

import yaml


class AgentContractError(RuntimeError):
    """The canonical contract is missing, unsafe or internally inconsistent."""


@dataclass(frozen=True)
class ContractDocument:
    identifier: str
    path: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.identifier, "path": self.path, "content": self.content}


@dataclass(frozen=True)
class AgentContractStatus:
    version: str
    digest: str
    rules: tuple[str, ...]
    skills: tuple[str, ...]
    prompts: tuple[str, ...]
    generated: tuple[str, ...]
    stale: tuple[str, ...]

    @property
    def synchronized(self) -> bool:
        return not self.stale

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "digest": self.digest,
            "rules": list(self.rules),
            "skills": list(self.skills),
            "prompts": list(self.prompts),
            "generated": list(self.generated),
            "stale": list(self.stale),
            "synchronized": self.synchronized,
        }


class AgentContractService:
    """Load one contract and generate Codex/Claude adapters from it."""

    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve(strict=True)
        bootstrap_root = self.repository_root / "agent_contract"
        if bootstrap_root.is_symlink():
            raise AgentContractError("canonical_root cannot be a symbolic link")
        try:
            resolved_bootstrap = bootstrap_root.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise AgentContractError("canonical contract root is unavailable") from error
        if (
            not resolved_bootstrap.is_relative_to(self.repository_root)
            or not resolved_bootstrap.is_dir()
        ):
            raise AgentContractError(
                "canonical contract root escapes repository or is not a directory"
            )
        bootstrap_manifest = resolved_bootstrap / "manifest.yaml"
        if bootstrap_manifest.is_symlink() or not bootstrap_manifest.is_file():
            raise AgentContractError("agent_contract/manifest.yaml must be a regular local file")
        raw = self._load_yaml(bootstrap_manifest)
        if not isinstance(raw, dict):
            raise AgentContractError("agent_contract/manifest.yaml must be a mapping")
        canonical_root = self._required_text(raw, "canonical_root")
        canonical_relative = self._safe_relative(canonical_root, "canonical_root")
        declared_root = self.repository_root.joinpath(*canonical_relative.parts)
        if declared_root.is_symlink():
            raise AgentContractError("canonical_root cannot be a symbolic link")
        try:
            self.contract_root = declared_root.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise AgentContractError("canonical_root is unavailable") from error
        if (
            self.contract_root != resolved_bootstrap
            or not self.contract_root.is_relative_to(self.repository_root)
            or not self.contract_root.is_dir()
        ):
            raise AgentContractError(
                "canonical_root must identify the directory containing agent_contract/manifest.yaml"
            )
        manifest_path = self._confined(self.contract_root / "manifest.yaml")
        raw = self._load_yaml(manifest_path)
        if not isinstance(raw, dict):
            raise AgentContractError("agent_contract/manifest.yaml must be a mapping")
        self.manifest: dict[str, Any] = raw
        self.version = self._required_text(raw, "version")
        self.contract_id = self._required_text(raw, "contract_id")
        self._supporting_paths: list[Path] = []
        self.rules = self._documents("rules")
        self.skills = self._documents("skills")
        self.prompts = self._documents("prompts")
        self.mcp_instructions = self._mcp_instructions()
        self._validate_mcp_contract()
        self._validate_supporting_files("examples", yaml_mode=True)
        self._validate_supporting_files("task_fixtures", yaml_mode=True)
        self._validate_supporting_files("schemas", json_mode=True)
        self.required_commands = self._string_list(raw.get("required_commands"), "commands")
        self._generated = self._expected_generated()
        self._validate_generated_manifest()

    def status(self) -> AgentContractStatus:
        stale = [
            path
            for path, expected in self._generated.items()
            if (self.repository_root / path).is_symlink()
            or not (self.repository_root / path).is_file()
            or (self.repository_root / path).read_text(encoding="utf-8") != expected
        ]
        stale.extend(self._unexpected_generated_paths())
        stale.extend(self._broken_generated_references())
        digest = sha256()
        digest.update((self.contract_root / "manifest.yaml").read_bytes())
        for document in (*self.rules, *self.skills, *self.prompts, self.mcp_instructions):
            digest.update(document.path.encode())
            digest.update(document.content.encode())
        for path in sorted(self._supporting_paths):
            digest.update(path.relative_to(self.contract_root).as_posix().encode())
            digest.update(path.read_bytes())
        return AgentContractStatus(
            self.version,
            digest.hexdigest(),
            tuple(document.identifier for document in self.rules),
            tuple(document.identifier for document in self.skills),
            tuple(document.identifier for document in self.prompts),
            tuple(self._generated),
            tuple(sorted(set(stale))),
        )

    def sync(self, *, check: bool = False) -> AgentContractStatus:
        status = self.status()
        if check:
            if status.stale:
                raise AgentContractError(
                    "generated agent adapters are stale: " + ", ".join(status.stale)
                )
            return status
        for relative, content in self._generated.items():
            self._atomic_write(self.repository_root / relative, content)
        return self.status()

    def _documents(self, key: str) -> tuple[ContractDocument, ...]:
        entries = self.manifest.get(key)
        if not isinstance(entries, list) or not entries:
            raise AgentContractError(f"manifest {key} must be a non-empty list")
        documents: list[ContractDocument] = []
        identifiers: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise AgentContractError(f"manifest {key} entries must be mappings")
            identifier = self._required_text(entry, "id")
            if identifier in identifiers:
                raise AgentContractError(f"duplicate {key} id: {identifier}")
            identifiers.add(identifier)
            relative = self._required_text(entry, "path")
            safe_relative = self._safe_relative(relative, f"manifest {key} path")
            path = self._confined(self.contract_root.joinpath(*safe_relative.parts))
            documents.append(
                ContractDocument(
                    identifier,
                    safe_relative.as_posix(),
                    path.read_text(encoding="utf-8"),
                )
            )
        return tuple(documents)

    def _mcp_instructions(self) -> ContractDocument:
        configuration = self.manifest.get("mcp")
        if not isinstance(configuration, dict):
            raise AgentContractError("manifest mcp must be a mapping")
        relative = self._required_text(configuration, "instructions")
        safe_relative = self._safe_relative(relative, "manifest mcp instructions")
        path = self._confined(self.contract_root.joinpath(*safe_relative.parts))
        return ContractDocument(
            "server_instructions",
            safe_relative.as_posix(),
            path.read_text(encoding="utf-8"),
        )

    def _validate_mcp_contract(self) -> None:
        expected = {
            "model_domain_concept": {"task", "evidence"},
            "review_ontology_change": {"base"},
            "connect_repository_to_enterprise_knowledge": {
                "repository",
                "business_question",
            },
        }
        actual = {document.identifier: document for document in self.prompts}
        if set(actual) != set(expected):
            raise AgentContractError("manifest prompts must define the three canonical MCP prompts")
        for identifier, arguments in expected.items():
            try:
                fields = {
                    field
                    for _, field, _, _ in Formatter().parse(actual[identifier].content)
                    if field is not None
                }
            except ValueError as error:
                raise AgentContractError(f"invalid MCP prompt template: {identifier}") from error
            if fields != arguments:
                raise AgentContractError(
                    f"MCP prompt {identifier} placeholders must be: " + ", ".join(sorted(arguments))
                )
        if any(
            field is not None for _, field, _, _ in Formatter().parse(self.mcp_instructions.content)
        ):
            raise AgentContractError("MCP server instructions cannot contain placeholders")

    def _validate_supporting_files(
        self,
        key: str,
        *,
        yaml_mode: bool = False,
        json_mode: bool = False,
    ) -> None:
        entries = self.manifest.get(key)
        if not isinstance(entries, list) or not entries:
            raise AgentContractError(f"manifest {key} must be a non-empty list")
        for entry in entries:
            relative = entry.get("path") if isinstance(entry, dict) else entry
            if not isinstance(relative, str) or not relative:
                raise AgentContractError(f"manifest {key} paths must be strings")
            safe_relative = self._safe_relative(relative, f"manifest {key} path")
            path = self._confined(self.contract_root.joinpath(*safe_relative.parts))
            self._supporting_paths.append(path)
            if yaml_mode and not isinstance(self._load_yaml(path), dict):
                raise AgentContractError(f"contract example must be a mapping: {relative}")
            if json_mode:
                try:
                    parsed = json.loads(path.read_text(encoding="utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise AgentContractError(f"invalid JSON schema: {relative}") from error
                if not isinstance(parsed, dict):
                    raise AgentContractError(f"contract schema must be an object: {relative}")

    def _expected_generated(self) -> dict[str, str]:
        compatibility = self.manifest.get("compatibility")
        if not isinstance(compatibility, dict):
            raise AgentContractError("manifest compatibility must be a mapping")
        expected: dict[str, str] = {}
        for agent, display in (("codex", "Codex"), ("claude_code", "Claude Code")):
            configuration = compatibility.get(agent)
            if not isinstance(configuration, dict):
                raise AgentContractError(f"missing compatibility entry: {agent}")
            instructions = self._required_text(configuration, "instructions")
            skills_root = self._required_text(configuration, "skills_root")
            instructions = self._safe_output(instructions, f"{agent} instructions")
            skills_root = self._safe_output(skills_root, f"{agent} skills_root")
            expected[instructions] = self._instruction_text(display)
            for skill in self.skills:
                expected[f"{skills_root}/{skill.identifier}/SKILL.md"] = skill.content
        return dict(sorted(expected.items()))

    def _validate_generated_manifest(self) -> None:
        generated = self.manifest.get("generated")
        if not isinstance(generated, dict):
            raise AgentContractError("manifest generated must be a mapping")
        instructions = generated.get("instructions")
        skills = generated.get("skills")
        if not isinstance(instructions, list) or not isinstance(skills, list):
            raise AgentContractError("manifest generated paths must be lists")
        declared_instructions = {
            self._safe_output(str(value), "generated instructions") for value in instructions
        }
        declared_skills = {self._safe_output(str(value), "generated skills") for value in skills}
        compatibility = self.manifest["compatibility"]
        expected_instructions = {
            self._safe_output(
                self._required_text(compatibility[agent], "instructions"),
                f"{agent} instructions",
            )
            for agent in ("codex", "claude_code")
        }
        expected_skills = {
            self._safe_output(
                self._required_text(compatibility[agent], "skills_root"),
                f"{agent} skills_root",
            )
            for agent in ("codex", "claude_code")
        }
        if declared_instructions != expected_instructions or declared_skills != expected_skills:
            raise AgentContractError("manifest generated paths must match compatibility adapters")

    def _unexpected_generated_paths(self) -> list[str]:
        compatibility = self.manifest["compatibility"]
        unexpected: list[str] = []
        expected = set(self._generated)
        for agent in ("codex", "claude_code"):
            configuration = compatibility[agent]
            skills_root = self.repository_root / configuration["skills_root"]
            if skills_root.is_symlink():
                unexpected.append(skills_root.relative_to(self.repository_root).as_posix())
                continue
            if not skills_root.is_dir():
                continue
            for path in skills_root.rglob("*"):
                if path.is_file() or path.is_symlink():
                    relative = path.relative_to(self.repository_root).as_posix()
                    if relative not in expected:
                        unexpected.append(relative)
        return unexpected

    def _instruction_text(self, agent: str) -> str:
        canonical = self.contract_root.relative_to(self.repository_root).as_posix()
        rules = "\n".join(
            f"- `{canonical}/{document.path}` ({document.identifier})" for document in self.rules
        )
        skills = "\n".join(
            f"- `{canonical}/{document.path}` ({document.identifier})" for document in self.skills
        )
        commands = "\n".join(f"- `{command}`" for command in self.required_commands)
        return (
            f"<!-- GENERATED from agent_contract/manifest.yaml v{self.version}; do not edit. -->\n"
            f"# Enterprise Ontology Workbench — {agent}\n\n"
            "Objetivo: descubrir, proponer y revisar conocimiento empresarial "
            "gobernado sin sustituir sus fuentes canónicas. "
            "RDF y Git son las fuentes canónicas. Buscá antes de crear, trabajá en "
            "`proposal/*`, adjuntá evidencia, validá y revisá el diff; nunca publiques "
            "o fusiones directamente en `main`. Usá MCP cuando esté disponible y el "
            "CLI como fallback determinista.\n\n"
            "## Reglas detalladas\n\n"
            f"{rules}\n\n"
            "## Skills canónicas\n\n"
            f"{skills}\n\n"
            "## Comandos obligatorios\n\n"
            f"{commands}\n"
        )

    def _confined(self, path: Path, *, allow_directory: bool = False) -> Path:
        try:
            lexical = path.relative_to(self.contract_root)
        except ValueError as error:
            raise AgentContractError(f"contract path escapes canonical_root: {path}") from error
        current = self.contract_root
        for part in lexical.parts:
            current = current / part
            if current.is_symlink():
                raise AgentContractError(f"contract path cannot contain a symbolic link: {path}")
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise AgentContractError(f"contract path is unavailable: {path}") from error
        expected_type = resolved.is_dir() if allow_directory else resolved.is_file()
        if not resolved.is_relative_to(self.contract_root) or not expected_type:
            raise AgentContractError(
                f"contract path escapes canonical_root or is not a file: {path}"
            )
        return resolved

    @staticmethod
    def _safe_relative(value: str, label: str) -> PurePosixPath:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise AgentContractError(f"{label} must be a normalized relative path")
        return path

    def _safe_output(self, value: str, label: str) -> str:
        relative = self._safe_relative(value, label)
        candidate = self.repository_root.joinpath(*relative.parts)
        current = self.repository_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise AgentContractError(f"{label} cannot contain a symbolic link")
        try:
            candidate.resolve(strict=False).relative_to(self.repository_root)
        except (OSError, RuntimeError, ValueError) as error:
            raise AgentContractError(f"{label} escapes repository") from error
        return relative.as_posix()

    def _broken_generated_references(self) -> list[str]:
        broken: list[str] = []
        instruction_paths = [
            configuration["instructions"]
            for configuration in self.manifest["compatibility"].values()
        ]
        for instruction in instruction_paths:
            instruction_path = self.repository_root / instruction
            if not instruction_path.is_file() or instruction_path.is_symlink():
                continue
            content = instruction_path.read_text(encoding="utf-8")
            for reference in re.findall(r"`([^`]+\.md)`", content):
                try:
                    relative = self._safe_relative(reference, "generated reference")
                    resolved = self.repository_root.joinpath(*relative.parts)
                    if resolved.is_symlink() or not resolved.resolve(strict=True).is_file():
                        raise OSError
                    if not resolved.resolve(strict=True).is_relative_to(self.repository_root):
                        raise OSError
                except (AgentContractError, OSError, RuntimeError):
                    broken.append(f"{instruction}:broken-reference:{reference}")
        return broken

    @staticmethod
    def _load_yaml(path: Path) -> object:
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
            raise AgentContractError(f"invalid YAML contract file: {path.name}") from error

    @staticmethod
    def _required_text(mapping: dict[str, Any], key: str) -> str:
        value = mapping.get(key)
        if not isinstance(value, str) or not value.strip():
            raise AgentContractError(f"manifest field {key} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _string_list(value: object, label: str) -> tuple[str, ...]:
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(item, str) for item in value)
        ):
            raise AgentContractError(f"manifest {label} must be a non-empty string list")
        return tuple(str(item) for item in value)

    def _atomic_write(self, path: Path, content: str) -> None:
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = parent.resolve(strict=True)
        if not resolved_parent.is_relative_to(self.repository_root):
            raise AgentContractError(f"generated path escapes repository: {path}")
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o644)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()
