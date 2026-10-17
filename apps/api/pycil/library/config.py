from typing import Annotated

from pydantic import Field

from pycil.utils.configuration import Policy, PositiveInt

PositiveSeconds = Annotated[float, Field(strict=True, gt=0)]


class LibraryConfig(Policy):
    # Quotas
    max_depth: PositiveInt = 20
    max_senses_per_deck: PositiveInt = 1000
    max_children_per_folder: PositiveInt = 500
    max_owned_nodes: PositiveInt = 2000
    max_owned_memberships: PositiveInt = 100_000
    max_scope_nodes: PositiveInt = 10_000
    max_scope_memberships: PositiveInt = 200_000

    # Pagination & View Limits
    page_size: PositiveInt = 50
    max_page_size: PositiveInt = 100
    inline_sources: PositiveInt = 5
    inline_examples: PositiveInt = 2
    max_query_chars: PositiveInt = 200
    max_summary_memberships: PositiveInt = 200_000

    # Runtime Timeouts
    statement_timeout_ms: PositiveInt = 3000
    scope_timeout_seconds: PositiveSeconds = 5.0
