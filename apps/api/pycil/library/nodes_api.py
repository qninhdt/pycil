"""Collection routes: node CRUD + folder analytics. Every route ownership-gated.

require_node_access is a hard dependency on every route — owner-only write,
owner-or-public read — closing the systemic IDOR gap. Stats stay inside pycil's
DB; CEFR distribution resolves content through the LexiReader port.
"""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.auth import current_user, optional_current_user
from pycil.account.schemas import CurrentUser
from pycil.lexicon.contracts import LexiReader
from pycil.lexicon.provider import get_lexi_client
from pycil.library import analytics, nodes, scope, views
from pycil.library.access import require_node_access
from pycil.library.models import NodeType
from pycil.library.schemas import (
    DeckCreate,
    FolderCreate,
    FolderItemRead,
    FolderStatsRead,
    HistoryBucketRead,
    NodeCreate,
    NodeMove,
    NodePageRead,
    NodeRead,
    NodeUpdate,
    NodeVisibilityUpdate,
    WeakSenseRead,
)
from pycil.platform.database import get_session

router = APIRouter(tags=["library"])


async def _read_node(session: AsyncSession, node_id: UUID, user: CurrentUser | None) -> NodeRead:
    node = await require_node_access(session, node_id, user, write=False)
    read = NodeRead.model_validate(node)
    viewer_id = user.id if user is not None else None
    read.path = await views.readable_path(session, node, viewer_id)
    if node.type == NodeType.DECK:
        read.item_count = (await analytics.deck_item_counts(session, [node.id])).get(node.id, 0)
    return read


async def _update_node(
    session: AsyncSession, node_id: UUID, body: NodeUpdate, user: CurrentUser
) -> NodeRead:
    node = await require_node_access(session, node_id, user, write=True)
    node = await nodes.update_node(session, node, name=body.name, description=body.description)
    return NodeRead.model_validate(node)


async def _move_node(
    session: AsyncSession, node_id: UUID, body: NodeMove, user: CurrentUser
) -> NodeRead:
    node = await require_node_access(session, node_id, user, write=True)
    if body.parent_node_id is not None:
        await require_node_access(session, body.parent_node_id, user, write=True)
    node = await nodes.move_node(session, node, body.parent_node_id)
    return NodeRead.model_validate(node)


async def _update_visibility(
    session: AsyncSession, node_id: UUID, body: NodeVisibilityUpdate, user: CurrentUser
) -> NodeRead:
    node = await require_node_access(session, node_id, user, write=True)
    node = await nodes.set_visibility(
        session,
        node,
        body.visibility,
        confirm_subtree_publication=body.confirm_subtree_publication,
    )
    return NodeRead.model_validate(node)


async def _delete_node(session: AsyncSession, node_id: UUID, user: CurrentUser) -> None:
    node = await require_node_access(session, node_id, user, write=True)
    await nodes.soft_delete_node(session, node)


@router.get("/folders", response_model=NodePageRead)
@router.get("/nodes", response_model=NodePageRead, include_in_schema=False)
async def list_nodes(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    parent_folder_id: UUID | None = Query(default=None, alias="parentFolderId"),
    parent_node_id: UUID | None = Query(
        default=None, alias="parentNodeId", include_in_schema=False
    ),
    cursor: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> NodePageRead:
    """List the caller's roots or one owned folder's immediate children."""
    p_fid = parent_folder_id if isinstance(parent_folder_id, UUID) else None
    p_nid = parent_node_id if isinstance(parent_node_id, UUID) else None
    effective_parent_id = p_fid or p_nid
    effective_cursor = cursor if isinstance(cursor, UUID) else None
    effective_limit = limit if isinstance(limit, int) else 50
    if effective_parent_id is not None:
        await require_node_access(session, effective_parent_id, user, write=True)
    page, next_cursor = await views.owned_children_page(
        session, user.id, effective_parent_id, cursor=effective_cursor, limit=effective_limit
    )
    counts = await analytics.deck_item_counts(
        session, [node.id for node in page if node.type == NodeType.DECK]
    )
    items: list[NodeRead] = []
    for node in page:
        read = NodeRead.model_validate(node)
        if node.type == NodeType.DECK:
            read.item_count = counts.get(node.id, 0)
        items.append(read)
    return NodePageRead(items=items, next_cursor=next_cursor)


@router.post("/folders", response_model=NodeRead, status_code=201)
async def create_folder(
    body: FolderCreate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    if body.parent_folder_id is not None:
        await require_node_access(session, body.parent_folder_id, user, write=True)
    node = await nodes.create_node(
        session,
        user.id,
        node_type=NodeType.FOLDER,
        name=body.name,
        parent_node_id=body.parent_folder_id,
        description=body.description,
        visibility=body.visibility,
        confirm_subtree_publication=body.confirm_subtree_publication,
    )
    return NodeRead.model_validate(node)


@router.post("/decks", response_model=NodeRead, status_code=201)
async def create_deck(
    body: DeckCreate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    if body.parent_folder_id is not None:
        await require_node_access(session, body.parent_folder_id, user, write=True)
    node = await nodes.create_node(
        session,
        user.id,
        node_type=NodeType.DECK,
        name=body.name,
        parent_node_id=body.parent_folder_id,
        description=body.description,
        visibility=body.visibility,
        confirm_subtree_publication=body.confirm_subtree_publication,
    )
    return NodeRead.model_validate(node)


@router.post("/nodes", response_model=NodeRead, status_code=201, include_in_schema=False)
async def create_node(
    body: NodeCreate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    if body.parent_node_id is not None:
        await require_node_access(session, body.parent_node_id, user, write=True)
    node = await nodes.create_node(
        session,
        user.id,
        node_type=body.type,
        name=body.name,
        parent_node_id=body.parent_node_id,
        target_node_id=body.target_node_id,
        description=body.description,
        visibility=body.visibility,
        confirm_subtree_publication=body.confirm_subtree_publication,
    )
    return NodeRead.model_validate(node)


@router.get("/folders/{folder_id}", response_model=NodeRead)
async def get_folder(
    folder_id: UUID,
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _read_node(session, folder_id, user)


@router.get("/decks/{deck_id}", response_model=NodeRead)
async def get_deck(
    deck_id: UUID,
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _read_node(session, deck_id, user)


@router.get("/nodes/{node_id}", response_model=NodeRead, include_in_schema=False)
async def get_node(
    node_id: UUID,
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _read_node(session, node_id, user)


@router.patch("/folders/{folder_id}", response_model=NodeRead)
async def update_folder(
    folder_id: UUID,
    body: NodeUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _update_node(session, folder_id, body, user)


@router.patch("/decks/{deck_id}", response_model=NodeRead)
async def update_deck(
    deck_id: UUID,
    body: NodeUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _update_node(session, deck_id, body, user)


@router.patch("/nodes/{node_id}", response_model=NodeRead, include_in_schema=False)
async def update_node(
    node_id: UUID,
    body: NodeUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _update_node(session, node_id, body, user)


@router.patch("/folders/{folder_id}/move", response_model=NodeRead)
async def move_folder(
    folder_id: UUID,
    body: NodeMove,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _move_node(session, folder_id, body, user)


@router.patch("/decks/{deck_id}/move", response_model=NodeRead)
async def move_deck(
    deck_id: UUID,
    body: NodeMove,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _move_node(session, deck_id, body, user)


@router.patch("/nodes/{node_id}/move", response_model=NodeRead, include_in_schema=False)
async def move_node(
    node_id: UUID,
    body: NodeMove,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _move_node(session, node_id, body, user)


@router.patch("/folders/{folder_id}/visibility", response_model=NodeRead)
async def update_folder_visibility(
    folder_id: UUID,
    body: NodeVisibilityUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _update_visibility(session, folder_id, body, user)


@router.patch("/decks/{deck_id}/visibility", response_model=NodeRead)
async def update_deck_visibility(
    deck_id: UUID,
    body: NodeVisibilityUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _update_visibility(session, deck_id, body, user)


@router.patch("/nodes/{node_id}/visibility", response_model=NodeRead, include_in_schema=False)
async def update_visibility(
    node_id: UUID,
    body: NodeVisibilityUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    return await _update_visibility(session, node_id, body, user)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> None:
    await _delete_node(session, folder_id, user)


@router.delete("/decks/{deck_id}", status_code=204)
async def delete_deck(
    deck_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> None:
    await _delete_node(session, deck_id, user)


@router.delete("/nodes/{node_id}", status_code=204, include_in_schema=False)
async def delete_node(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> None:
    await _delete_node(session, node_id, user)


@router.get("/folders/{folder_id}/items", response_model=list[FolderItemRead])
async def folder_items(
    folder_id: UUID,
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[FolderItemRead]:
    await require_node_access(session, folder_id, user, write=False)
    sense_ids = (
        await scope.cached_sense_ids(session, folder_id, user.id if user is not None else None)
    )[offset : offset + limit]
    views = await client.get_senses(sense_ids)
    return [
        FolderItemRead(
            sense_id=view.sense_id,
            definition=view.definition,
            tier=view.tier,
            cefr_level=view.cefr_level,
        )
        for view in views
        if view.sense_id is not None
    ]


@router.get("/me/stats", response_model=FolderStatsRead)
async def global_stats(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    folder_id: Annotated[UUID | None, Query(alias="folderId")] = None,
    deck_id: Annotated[UUID | None, Query(alias="deckId")] = None,
    node_id: Annotated[UUID | None, Query(alias="nodeId", include_in_schema=False)] = None,
) -> FolderStatsRead:
    """Totals over the account, or one readable folder/deck scope when supplied."""
    f_id = folder_id if isinstance(folder_id, UUID) else None
    d_id = deck_id if isinstance(deck_id, UUID) else None
    n_id = node_id if isinstance(node_id, UUID) else None
    target_id = f_id or d_id or n_id
    sense_ids = await _node_scope(session, user, target_id)
    result = await analytics.stats_for_scope(session, user.id, sense_ids)
    return FolderStatsRead(
        total=result.total,
        learned=result.learned,
        mastered=result.mastered,
        avg_mastery=result.avg_mastery,
    )


@router.get("/me/history", response_model=list[HistoryBucketRead])
async def global_history(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    bucket: Literal["day"] = "day",
    folder_id: Annotated[UUID | None, Query(alias="folderId")] = None,
    deck_id: Annotated[UUID | None, Query(alias="deckId")] = None,
    node_id: Annotated[UUID | None, Query(alias="nodeId", include_in_schema=False)] = None,
) -> list[HistoryBucketRead]:
    """Review history over the account, or one readable folder/deck scope."""
    del bucket
    start, end = views.history_window(from_date, to_date)
    f_id = folder_id if isinstance(folder_id, UUID) else None
    d_id = deck_id if isinstance(deck_id, UUID) else None
    n_id = node_id if isinstance(node_id, UUID) else None
    target_id = f_id or d_id or n_id
    sense_ids = await _node_scope(session, user, target_id)
    buckets = await analytics.history_buckets(session, user.id, sense_ids, start, end)
    return views.history_read(buckets)


@router.get("/me/cefr", response_model=dict[str, int])
async def global_cefr(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
    folder_id: Annotated[UUID | None, Query(alias="folderId")] = None,
    deck_id: Annotated[UUID | None, Query(alias="deckId")] = None,
    node_id: Annotated[UUID | None, Query(alias="nodeId", include_in_schema=False)] = None,
) -> dict[str, int]:
    """CEFR distribution over the account, or one readable folder/deck scope."""
    f_id = folder_id if isinstance(folder_id, UUID) else None
    d_id = deck_id if isinstance(deck_id, UUID) else None
    n_id = node_id if isinstance(node_id, UUID) else None
    target_id = f_id or d_id or n_id
    sense_ids = await _node_scope(session, user, target_id)
    if sense_ids is None:
        sense_ids = await views.tracked_sense_ids(session, user.id)
    return await analytics.cefr_distribution(client, sense_ids)


@router.get("/me/weakest", response_model=list[WeakSenseRead])
async def global_weakest(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
    limit: int = Query(default=10, ge=1, le=100),
    folder_id: Annotated[UUID | None, Query(alias="folderId")] = None,
    deck_id: Annotated[UUID | None, Query(alias="deckId")] = None,
    node_id: Annotated[UUID | None, Query(alias="nodeId", include_in_schema=False)] = None,
) -> list[WeakSenseRead]:
    """Exact database top-K weakest senses over the selected scope."""
    f_id = folder_id if isinstance(folder_id, UUID) else None
    d_id = deck_id if isinstance(deck_id, UUID) else None
    n_id = node_id if isinstance(node_id, UUID) else None
    target_id = f_id or d_id or n_id
    sense_ids = await _node_scope(session, user, target_id)
    weak = await analytics.weakest_senses(session, user.id, sense_ids, limit=limit)
    return await views.hydrate_weakest(client, weak)


async def _node_scope(
    session: AsyncSession, user: CurrentUser, node_id: UUID | None
) -> list[int] | None:
    """Resolve one optional node scope through the canonical read gate."""
    if node_id is None:
        return None
    await require_node_access(session, node_id, user, write=False)
    return await scope.cached_sense_ids(session, node_id, user.id)
