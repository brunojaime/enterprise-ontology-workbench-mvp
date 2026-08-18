"""Thin HTTP adapter for controlled proposal authoring and Git review."""

from typing import Annotated

from fastapi import APIRouter, Depends
from ontology_core import (
    DeprecationDraft,
    FormSchemaService,
    GitWorkspaceService,
    IndividualDraft,
    ProposalReviewService,
    RelationDraft,
    RelationIdentity,
    SearchConfirmation,
    TermDraft,
    TermWriter,
)

from enterprise_ontology_api.dependencies import runtime_manager, runtime_snapshot
from enterprise_ontology_api.errors import ApiProblem, error_responses
from enterprise_ontology_api.models import (
    BranchRequest,
    CommitRequest,
    CommitResultModel,
    DeprecationRequest,
    EditableResourceModel,
    FormSchemaModel,
    GitStatusModel,
    IndividualWriteRequest,
    ProposalReviewModel,
    PullRequestRequest,
    PullRequestResultModel,
    RelationDeleteRequest,
    RelationWriteRequest,
    SearchConfirmationModel,
    SemanticDiffModel,
    TermWriteRequest,
    WriteResultModel,
)
from enterprise_ontology_api.runtime import RuntimeManager, RuntimeSnapshot

router = APIRouter(prefix="/api", tags=["editing"])


def _workspace(manager: RuntimeManager, *, require_write: bool = False) -> GitWorkspaceService:
    if require_write and not manager.settings.write_enabled:
        raise ApiProblem(
            403,
            "authoring.disabled",
            "Repository writing is disabled for this API runtime.",
            details={"setting": "EOW_WRITE_ENABLED"},
        )
    return GitWorkspaceService(
        manager.settings.repository_root,
        manager.settings.knowledge_root,
    )


def _writer(manager: RuntimeManager, snapshot: RuntimeSnapshot) -> TermWriter:
    return TermWriter(
        snapshot.store,
        _workspace(manager, require_write=True),
        snapshot.query,
    )


def _read_writer(snapshot: RuntimeSnapshot) -> TermWriter:
    return TermWriter(snapshot.store, None)


def _search(value: SearchConfirmationModel) -> SearchConfirmation:
    return SearchConfirmation(
        query=value.query,
        confirmed=value.confirmed,
        search_id=value.search_id,
    )


@router.get("/git/status", response_model=GitStatusModel, responses=error_responses(403, 409))
def git_status(
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
) -> dict[str, object]:
    return _workspace(manager).status().to_dict()


@router.get("/authoring/forms", response_model=list[FormSchemaModel])
def authoring_forms(
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> list[dict[str, object]]:
    return [schema.to_dict() for schema in FormSchemaService(snapshot.store).schemas()]


@router.get(
    "/authoring/state",
    response_model=EditableResourceModel,
    responses=error_responses(409, 422),
)
def authoring_state(
    iri: str,
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    return _read_writer(snapshot).editable_resource(iri).to_dict()


@router.post("/git/branch", response_model=GitStatusModel, responses=error_responses(403, 409, 422))
def git_branch(
    request: BranchRequest,
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
) -> dict[str, object]:
    status = _workspace(manager, require_write=True).switch_proposal(
        request.branch, create=request.create
    )
    manager.reload()
    return status.to_dict()


@router.post(
    "/resources", response_model=WriteResultModel, responses=error_responses(403, 409, 422)
)
@router.patch(
    "/resources", response_model=WriteResultModel, responses=error_responses(403, 409, 422)
)
def write_term(
    request: TermWriteRequest,
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    result = _writer(manager, snapshot).save_term(
        TermDraft(
            iri=request.iri,
            module_id=request.module_id,
            kind=request.kind,
            preferred_label_es=request.preferred_label_es,
            definition_es=request.definition_es,
            evidence=request.evidence,
            author=request.author,
            search=_search(request.search),
            alternative_labels_es=tuple(request.alternative_labels_es),
            status=request.status,
            reading_direction_es=request.reading_direction_es,
            valid_example=request.valid_example,
            domain=request.domain,
            range=request.range,
            question_text_es=request.question_text_es,
            acceptance_criterion_es=request.acceptance_criterion_es,
            form_values=tuple(
                sorted(
                    (
                        key,
                        tuple(map(str, value if isinstance(value, list) else [value])),
                    )
                    for key, value in request.form_values.items()
                )
            ),
        )
    )
    manager.reload()
    return result.to_dict()


@router.post(
    "/resources/individual",
    response_model=WriteResultModel,
    responses=error_responses(403, 409, 422),
)
def write_individual(
    request: IndividualWriteRequest,
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    result = _writer(manager, snapshot).save_individual(
        IndividualDraft(
            iri=request.iri,
            class_iri=request.class_iri,
            source_id=request.source_id,
            preferred_label_es=request.preferred_label_es,
            alternative_labels_es=tuple(request.alternative_labels_es),
            evidence=request.evidence,
            author=request.author,
            search=_search(request.search),
            status=request.status,
            form_values=tuple(
                sorted(
                    (
                        key,
                        tuple(map(str, value if isinstance(value, list) else [value])),
                    )
                    for key, value in request.form_values.items()
                )
            ),
        )
    )
    manager.reload()
    return result.to_dict()


@router.post(
    "/relations", response_model=WriteResultModel, responses=error_responses(403, 409, 422)
)
def write_relation(
    request: RelationWriteRequest,
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    result = _writer(manager, snapshot).save_relation(RelationDraft(**request.model_dump()))
    manager.reload()
    return result.to_dict()


@router.delete(
    "/relations/draft", response_model=WriteResultModel, responses=error_responses(403, 409, 422)
)
def delete_relation(
    request: RelationDeleteRequest,
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    result = _writer(manager, snapshot).delete_draft_relation(
        RelationIdentity(**request.model_dump())
    )
    manager.reload()
    return result.to_dict()


@router.post(
    "/resources/deprecate",
    response_model=WriteResultModel,
    responses=error_responses(403, 409, 422),
)
def deprecate_resource(
    request: DeprecationRequest,
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    result = _writer(manager, snapshot).deprecate(DeprecationDraft(**request.model_dump()))
    manager.reload()
    return result.to_dict()


@router.get("/diff", response_model=SemanticDiffModel, responses=error_responses(403, 409, 422))
def semantic_diff(
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    return ProposalReviewService(snapshot.store, _workspace(manager)).review().diff.to_dict()


@router.get("/review", response_model=ProposalReviewModel, responses=error_responses(403, 409, 422))
def proposal_review(
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
    snapshot: Annotated[RuntimeSnapshot, Depends(runtime_snapshot)],
) -> dict[str, object]:
    return ProposalReviewService(snapshot.store, _workspace(manager)).review().to_dict()


@router.post(
    "/git/commit", response_model=CommitResultModel, responses=error_responses(403, 409, 422)
)
def git_commit(
    request: CommitRequest,
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
) -> dict[str, object]:
    result = manager.commit_proposal(
        _workspace(manager, require_write=True),
        module=request.module,
        summary=request.summary,
        exception_reason=request.exception_reason,
    )
    return result.to_dict()


@router.post(
    "/git/pull_request",
    response_model=PullRequestResultModel,
    responses=error_responses(403, 409, 422),
)
def git_pull_request(
    request: PullRequestRequest,
    manager: Annotated[RuntimeManager, Depends(runtime_manager)],
) -> dict[str, str | None]:
    return (
        _workspace(manager, require_write=True)
        .create_pull_request(
            title=request.title,
            body=request.body,
            draft=request.draft,
        )
        .to_dict()
    )
