from pycil.infrastructure.configuration import Policy, PositiveInt


class LibraryPolicy(Policy):
    max_depth: PositiveInt
    page_size: PositiveInt
    max_senses_per_deck: PositiveInt
    max_children_per_folder: PositiveInt
    max_owned_nodes: PositiveInt
    max_owned_memberships: PositiveInt
    max_scope_nodes: PositiveInt
    max_scope_memberships: PositiveInt
    statement_timeout_ms: PositiveInt
    scope_timeout_seconds: PositiveInt
