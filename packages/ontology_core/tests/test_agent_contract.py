from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from ontology_core import AgentContractError, AgentContractService

ROOT = Path(__file__).parents[3]


def _contract_checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    root.mkdir()
    shutil.copytree(ROOT / "agent_contract", root / "agent_contract")
    service = AgentContractService(root)
    service.sync()
    return root


def test_contract_loads_every_canonical_document_and_is_synchronized() -> None:
    first = AgentContractService(ROOT)
    second = AgentContractService(ROOT)

    assert first.status() == second.status()
    assert first.status().synchronized
    assert {document.identifier for document in first.rules} == {
        "principles",
        "modeling_decision_tree",
        "change_protocol",
        "prohibited_patterns",
    }
    assert {document.identifier for document in first.skills} == {
        "ontology_discover",
        "ontology_author",
        "ontology_review",
    }
    assert {document.identifier for document in first.prompts} == {
        "model_domain_concept",
        "review_ontology_change",
        "connect_repository_to_enterprise_knowledge",
    }
    assert "RDF y Git" in first.mcp_instructions.content


def test_sync_detects_and_repairs_divergence(tmp_path: Path) -> None:
    root = _contract_checkout(tmp_path)
    generated = root / ".agents/skills/ontology_author/SKILL.md"
    generated.write_text("diverged\n", encoding="utf-8")
    service = AgentContractService(root)

    assert generated.relative_to(root).as_posix() in service.status().stale
    with pytest.raises(AgentContractError, match="stale"):
        service.sync(check=True)

    assert service.sync().synchronized
    service.sync(check=True)


def test_sync_publishes_adapters_readable_by_the_packaged_runtime(tmp_path: Path) -> None:
    root = _contract_checkout(tmp_path)

    for relative in AgentContractService(root).status().generated:
        assert (root / relative).stat().st_mode & 0o044 == 0o044


def test_check_rejects_an_unexpected_generated_skill(tmp_path: Path) -> None:
    root = _contract_checkout(tmp_path)
    unexpected = root / ".agents/skills/unmanaged/SKILL.md"
    unexpected.parent.mkdir()
    unexpected.write_text("unmanaged\n", encoding="utf-8")

    service = AgentContractService(root)

    assert ".agents/skills/unmanaged/SKILL.md" in service.status().stale
    with pytest.raises(AgentContractError, match="unmanaged"):
        service.sync(check=True)


def test_contract_rejects_a_supporting_file_symlink_escape(tmp_path: Path) -> None:
    root = _contract_checkout(tmp_path)
    outside = tmp_path / "outside.yaml"
    outside.write_text("id: escaped\n", encoding="utf-8")
    example = root / "agent_contract/examples/class.yaml"
    example.unlink()
    example.symlink_to(outside)

    with pytest.raises(AgentContractError, match="symbolic link"):
        AgentContractService(root)


def test_contract_rejects_parent_traversal_even_when_target_is_inside_repository(
    tmp_path: Path,
) -> None:
    root = _contract_checkout(tmp_path)
    outside = root / "outside.md"
    outside.write_text("# Not canonical\n", encoding="utf-8")
    manifest = root / "agent_contract/manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "path: rules/principles.md",
            "path: ../outside.md",
        ),
        encoding="utf-8",
    )

    with pytest.raises(AgentContractError, match="normalized relative path"):
        AgentContractService(root)


@pytest.mark.parametrize("canonical_root", [".", "..", "other", "/tmp/agent_contract"])
def test_contract_rejects_an_incoherent_or_escaping_canonical_root(
    tmp_path: Path,
    canonical_root: str,
) -> None:
    root = _contract_checkout(tmp_path)
    if canonical_root == "other":
        (root / "other").mkdir()
    manifest = root / "agent_contract/manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "canonical_root: agent_contract",
            f"canonical_root: {canonical_root}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(AgentContractError, match="canonical_root"):
        AgentContractService(root)


def test_contract_rejects_a_symlinked_canonical_root(tmp_path: Path) -> None:
    root = _contract_checkout(tmp_path)
    canonical = root / "agent_contract"
    moved = root / "real_contract"
    canonical.rename(moved)
    canonical.symlink_to(moved, target_is_directory=True)

    with pytest.raises(AgentContractError, match="symbolic link"):
        AgentContractService(root)


def test_generated_instructions_reference_resolvable_canonical_documents(
    tmp_path: Path,
) -> None:
    root = _contract_checkout(tmp_path)

    for instruction in (root / "AGENTS.md", root / "CLAUDE.md"):
        text = instruction.read_text(encoding="utf-8")
        assert "`agent_contract/rules/principles.md`" in text
        assert "`agent_contract/skills/ontology_author/SKILL.md`" in text

    broken = root / "AGENTS.md"
    broken.write_text(
        broken.read_text(encoding="utf-8").replace(
            "agent_contract/rules/principles.md",
            "agent_contract/rules/missing.md",
        ),
        encoding="utf-8",
    )
    status = AgentContractService(root).status()
    assert any("broken-reference" in item for item in status.stale)
    with pytest.raises(AgentContractError, match="broken-reference"):
        AgentContractService(root).sync(check=True)


def test_contract_rejects_a_divergent_mcp_prompt_signature(tmp_path: Path) -> None:
    root = _contract_checkout(tmp_path)
    prompt = root / "agent_contract/prompts/model_domain_concept.md"
    prompt.write_text(prompt.read_text(encoding="utf-8").replace("{evidence}", "evidencia"))

    with pytest.raises(AgentContractError, match="placeholders"):
        AgentContractService(root)
