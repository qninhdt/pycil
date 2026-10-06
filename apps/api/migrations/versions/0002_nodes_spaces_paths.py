"""Preserve canonical node identities while moving publication into system spaces.

Requires a quiesced API. Frozen SQL only: no imports from current application models.
Rollback after this breaking placement change requires the pre-upgrade backup.
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "0002_nodes_spaces_paths"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def execute(sql):
    return op.get_bind().execute(sa.text(sql))


def upgrade():
    # Capture actual old ancestor-based publication BEFORE changing any placement.
    invalid = execute("""
        SELECT child.id FROM collection_nodes child JOIN collection_nodes parent
          ON parent.id = child.parent_id
        WHERE parent.owner_id != child.owner_id OR parent.type != 'FOLDER' LIMIT 1
    """).scalar()
    if invalid:
        raise RuntimeError(f"Invalid node parent/owner; repair before migration: {invalid}")
    invalid_reference = execute("""
        SELECT source.id FROM collection_nodes source JOIN collection_nodes target
          ON target.id = source.reference_id
        WHERE target.type NOT IN ('FOLDER', 'DECK') LIMIT 1
    """).scalar()
    if invalid_reference:
        raise RuntimeError(
            f"Invalid reference target; repair before migration: {invalid_reference}"
        )
    execute("""
        CREATE TEMP TABLE legacy_node_placement ON COMMIT DROP AS
        WITH RECURSIVE walk AS (
          SELECT id, parent_id, owner_id, deleted_at IS NULL AS active,
                 visibility = 'PUBLIC' AND deleted_at IS NULL AS published
          FROM collection_nodes WHERE parent_id IS NULL
          UNION ALL
          SELECT n.id, n.parent_id, n.owner_id, w.active AND n.deleted_at IS NULL,
                 w.active AND n.deleted_at IS NULL AND (w.published OR n.visibility = 'PUBLIC')
          FROM collection_nodes n JOIN walk w ON n.parent_id = w.id
        ) SELECT * FROM walk
    """)
    missing = execute("""
        SELECT id FROM collection_nodes
        WHERE id NOT IN (SELECT id FROM legacy_node_placement) LIMIT 1
    """).scalar()
    if missing:
        raise RuntimeError(f"Cyclic or detached node ancestry; repair before migration: {missing}")

    op.rename_table("collection_nodes", "nodes")
    # PostgreSQL keeps old constraint/index names after a table rename.
    for constraint in (
        "pk_collection_nodes",
        "fk_collection_nodes_owner_id_users",
        "fk_collection_nodes_reference_id_collection_nodes",
        "ck_collection_nodes_nodetype",
        "ck_collection_nodes_not_own_parent",
        "ck_collection_nodes_not_own_reference",
        "ck_collection_nodes_reference_shape",
    ):
        name = constraint.replace("collection_nodes", "nodes")
        execute(f'ALTER TABLE nodes RENAME CONSTRAINT "{constraint}" TO "{name}"')
    execute("""
        ALTER TABLE deck_senses RENAME CONSTRAINT fk_deck_senses_deck_id_collection_nodes
        TO fk_deck_senses_deck_id_nodes
    """)
    execute("ALTER INDEX ix_collection_nodes_parent_id RENAME TO ix_nodes_parent_id")
    execute("ALTER INDEX ix_collection_nodes_reference_id RENAME TO ix_nodes_reference_id")
    op.drop_index("ix_nodes_public_root_order", table_name="nodes")
    op.drop_index("ix_nodes_owner_parent_order", table_name="nodes")
    op.drop_constraint(
        "fk_collection_nodes_parent_id_collection_nodes", "nodes", type_="foreignkey"
    )
    op.add_column("nodes", sa.Column("role", sa.String(14), nullable=True))
    op.add_column("nodes", sa.Column("space", sa.String(9), nullable=True))
    execute("""
        UPDATE nodes n SET role = 'NORMAL',
            space = CASE WHEN old.published THEN 'PUBLISHED' ELSE 'PERSONAL' END,
            deleted_at = CASE WHEN old.active THEN n.deleted_at
                             ELSE coalesce(n.deleted_at, CURRENT_TIMESTAMP) END
        FROM legacy_node_placement old WHERE old.id = n.id
    """)
    execute("""
        CREATE TEMP TABLE new_library_roots ON COMMIT DROP AS
        SELECT id AS owner_id, gen_random_uuid() AS library_id,
               gen_random_uuid() AS personal_id, gen_random_uuid() AS published_id FROM users
    """)
    execute("""
        INSERT INTO nodes(id, owner_id, type, parent_id, name, visibility, role, space,
                          created_at, updated_at)
        SELECT library_id, owner_id, 'FOLDER', NULL, 'Library', 'PRIVATE', 'LIBRARY_ROOT',
               'LIBRARY', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM new_library_roots
        UNION ALL
        SELECT personal_id, owner_id, 'FOLDER', library_id, 'Personal', 'PRIVATE', 'PERSONAL_ROOT',
               'PERSONAL', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM new_library_roots
        UNION ALL
        SELECT published_id, owner_id, 'FOLDER', library_id, 'Published', 'PRIVATE',
               'PUBLISHED_ROOT',
               'PUBLISHED', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM new_library_roots
    """)
    execute("""
        UPDATE nodes n SET parent_id = r.personal_id FROM new_library_roots r
        WHERE n.owner_id = r.owner_id AND n.role = 'NORMAL' AND n.parent_id IS NULL
    """)
    execute("""
        CREATE TEMP TABLE publication_frontiers ON COMMIT DROP AS
        SELECT old.*, coalesce(old.parent_id, r.personal_id) AS previous_parent
        FROM legacy_node_placement old JOIN new_library_roots r ON r.owner_id = old.owner_id
        LEFT JOIN legacy_node_placement parent ON parent.id = old.parent_id
        WHERE old.published AND NOT coalesce(parent.published, false)
    """)
    execute("""
        UPDATE nodes n SET parent_id = r.published_id
        FROM publication_frontiers f JOIN new_library_roots r ON r.owner_id = f.owner_id
        WHERE n.id = f.id
    """)
    # Optional private shortcuts preserve the old organization without cloning decks.
    execute("""
        INSERT INTO nodes(id, owner_id, type, parent_id, reference_id, name, description,
                          visibility, role, space, created_at, updated_at)
        SELECT gen_random_uuid(), n.owner_id, 'REFERENCE', f.previous_parent, n.id,
               n.name, n.description, 'PRIVATE', 'NORMAL', 'PERSONAL',
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM publication_frontiers f JOIN nodes n ON n.id = f.id WHERE n.type != 'REFERENCE'
    """)
    # All owners have been assigned before cross-owner reference validation.
    repaired = execute("""
        WITH repaired AS (
          UPDATE nodes n SET parent_id = r.personal_id, space = 'PERSONAL'
          FROM new_library_roots r
          WHERE n.owner_id = r.owner_id AND n.type = 'REFERENCE' AND n.space = 'PUBLISHED'
            AND NOT EXISTS (SELECT 1 FROM nodes t WHERE t.id = n.reference_id
                            AND t.deleted_at IS NULL AND t.space = 'PUBLISHED'
                            AND t.type IN ('FOLDER', 'DECK'))
          RETURNING n.id
        ) SELECT count(*) FROM repaired
    """).scalar()
    if repaired:
        log.warning("Moved %s unavailable Published references into Personal", repaired)

    # Recompute from final placements, not the retired per-node policy.
    execute("""
        WITH RECURSIVE walk AS (
          SELECT id, space FROM nodes WHERE role = 'LIBRARY_ROOT'
          UNION ALL
          SELECT n.id, CASE WHEN n.role IN ('PERSONAL_ROOT', 'PUBLISHED_ROOT')
                           THEN n.space ELSE w.space END
          FROM nodes n JOIN walk w ON n.parent_id = w.id
        ) UPDATE nodes n SET space = w.space FROM walk w WHERE n.id = w.id
    """)
    op.drop_constraint(op.f("ck_collection_nodes_visibility"), "nodes", type_="check")
    op.drop_column("nodes", "visibility")
    op.alter_column("nodes", "role", nullable=False)
    op.alter_column("nodes", "space", nullable=False)
    for name, expression in (
        ("noderole", "role IN ('NORMAL', 'LIBRARY_ROOT', 'PERSONAL_ROOT', 'PUBLISHED_ROOT')"),
        ("nodespace", "space IN ('LIBRARY', 'PERSONAL', 'PUBLISHED')"),
        ("root_shape", "(role = 'LIBRARY_ROOT') = (parent_id IS NULL)"),
        ("system_folder", "role = 'NORMAL' OR type = 'FOLDER'"),
    ):
        op.create_check_constraint(op.f(f"ck_nodes_{name}"), "nodes", expression)
    op.create_unique_constraint(op.f("uq_nodes_owner_id"), "nodes", ["owner_id", "id"])
    op.create_foreign_key(
        op.f("fk_nodes_owner_id_nodes"),
        "nodes",
        "nodes",
        ["owner_id", "parent_id"],
        ["owner_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_nodes_owner_role",
        "nodes",
        ["owner_id", "role"],
        unique=True,
        postgresql_where=sa.text("role != 'NORMAL'"),
    )
    op.create_index(
        "ix_nodes_owner_parent_order",
        "nodes",
        ["owner_id", "parent_id", "created_at", "id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_nodes_published_order",
        "nodes",
        ["created_at", "id"],
        postgresql_where=sa.text("deleted_at IS NULL AND space = 'PUBLISHED' AND role = 'NORMAL'"),
    )
    op.create_table(
        "node_paths",
        sa.Column("ancestor_id", sa.Uuid(), nullable=False),
        sa.Column("descendant_id", sa.Uuid(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("ancestor_id", "descendant_id", name=op.f("pk_node_paths")),
        sa.ForeignKeyConstraint(
            ["ancestor_id"],
            ["nodes.id"],
            ondelete="CASCADE",
            name=op.f("fk_node_paths_ancestor_id_nodes"),
        ),
        sa.ForeignKeyConstraint(
            ["descendant_id"],
            ["nodes.id"],
            ondelete="CASCADE",
            name=op.f("fk_node_paths_descendant_id_nodes"),
        ),
        sa.CheckConstraint("depth >= 0", name=op.f("ck_node_paths_nonnegative_depth")),
        sa.CheckConstraint(
            "(ancestor_id = descendant_id) = (depth = 0)", name=op.f("ck_node_paths_self_depth")
        ),
    )
    op.create_index("ix_node_paths_descendant", "node_paths", ["descendant_id", "ancestor_id"])
    execute("""
        WITH RECURSIVE closure AS (
          SELECT id AS ancestor_id, id AS descendant_id, 0 AS depth FROM nodes
          WHERE deleted_at IS NULL
          UNION ALL
          SELECT c.ancestor_id, n.id, c.depth + 1 FROM closure c
          JOIN nodes n ON n.parent_id = c.descendant_id WHERE n.deleted_at IS NULL
        ) INSERT INTO node_paths SELECT * FROM closure
    """)
    over_limit = execute("""
        SELECT count(*) FROM node_paths p JOIN nodes n ON n.id = p.ancestor_id
        WHERE n.role = 'LIBRARY_ROOT' AND p.depth > 20
    """).scalar()
    if over_limit:
        log.warning("Preserved %s nodes deeper than 20; reject growth, permit repair", over_limit)
    for label, sql in (
        (
            "owners over the node quota",
            """
          SELECT count(*) FROM (SELECT owner_id FROM nodes
          WHERE deleted_at IS NULL AND role != 'LIBRARY_ROOT'
          GROUP BY owner_id HAVING count(*) > 2000) excess
        """,
        ),
        (
            "folders over the child quota",
            """
          SELECT count(*) FROM (SELECT parent_id FROM nodes WHERE deleted_at IS NULL
          GROUP BY parent_id HAVING count(*) > 500) excess
        """,
        ),
        (
            "decks over the membership quota",
            """
          SELECT count(*) FROM (SELECT d.deck_id FROM deck_senses d JOIN nodes n ON n.id = d.deck_id
          WHERE n.deleted_at IS NULL GROUP BY d.deck_id HAVING count(*) > 1000) excess
        """,
        ),
        (
            "owners over the membership quota",
            """
          SELECT count(*) FROM (SELECT n.owner_id FROM deck_senses d
          JOIN nodes n ON n.id = d.deck_id
          WHERE n.deleted_at IS NULL GROUP BY n.owner_id HAVING count(*) > 100000) excess
        """,
        ),
    ):
        count = execute(sql).scalar()
        if count:
            log.warning("Preserved %s %s; reject growth, permit repair", count, label)


def downgrade():
    raise RuntimeError(
        "Restore the pre-upgrade backup: old publication placement is not reversible"
    )
