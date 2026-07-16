"""Add hierarchy structural generations and safe reference constraints.

Revision ID: 0002_hierarchy_integrity
Revises: 0001_baseline
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_hierarchy_integrity"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _assert_hierarchy_preflight()
    op.add_column(
        "nodes",
        sa.Column("structural_generation", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index("ix_nodes_target_node_id", "nodes", ["target_node_id"])
    op.create_check_constraint(
        "ck_nodes_reference_target_shape",
        "nodes",
        "(type = 'REFERENCE' AND target_node_id IS NOT NULL) "
        "OR (type <> 'REFERENCE' AND target_node_id IS NULL)",
    )


def downgrade() -> None:
    raise RuntimeError("0002 is additive; rollback application code or forward-fix, never drop live schema")


def _assert_hierarchy_preflight() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM nodes
                WHERE (type = 'REFERENCE' AND target_node_id IS NULL)
                   OR (type <> 'REFERENCE' AND target_node_id IS NOT NULL)
            ) THEN
                RAISE EXCEPTION
                    '0002 hierarchy preflight failed: invalid reference target shape';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM nodes child
                JOIN nodes parent ON parent.id = child.parent_node_id
                WHERE child.author_id <> parent.author_id
            ) THEN
                RAISE EXCEPTION
                    '0002 hierarchy preflight failed: cross-owner ownership edge';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM nodes child
                JOIN nodes parent ON parent.id = child.parent_node_id
                WHERE parent.type <> 'FOLDER'
            ) THEN
                RAISE EXCEPTION
                    '0002 hierarchy preflight failed: non-folder parent';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM deck_senses membership
                JOIN nodes node ON node.id = membership.node_id
                WHERE node.type <> 'DECK'
            ) THEN
                RAISE EXCEPTION
                    '0002 hierarchy preflight failed: membership on non-deck';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM nodes reference
                LEFT JOIN nodes target ON target.id = reference.target_node_id
                WHERE reference.type = 'REFERENCE'
                  AND (
                      target.id IS NULL
                      OR target.deleted_at IS NOT NULL
                      OR target.type <> 'DECK'
                      OR (
                          target.author_id <> reference.author_id
                          AND target.visibility <> 'PUBLIC'
                      )
                  )
            ) THEN
                RAISE EXCEPTION
                    '0002 hierarchy preflight failed: unavailable reference target';
            END IF;
            IF EXISTS (
                WITH RECURSIVE ancestry AS (
                    SELECT id AS start_id, id, parent_node_id, ARRAY[id] AS path
                    FROM nodes
                    WHERE parent_node_id IS NOT NULL
                    UNION ALL
                    SELECT ancestry.start_id, parent.id, parent.parent_node_id,
                           ancestry.path || parent.id
                    FROM ancestry
                    JOIN nodes parent ON parent.id = ancestry.parent_node_id
                    WHERE NOT parent.id = ANY(ancestry.path)
                )
                SELECT 1
                FROM ancestry
                JOIN nodes parent ON parent.id = ancestry.parent_node_id
                WHERE parent.id = ANY(ancestry.path)
            ) THEN
                RAISE EXCEPTION '0002 hierarchy preflight failed: ownership cycle';
            END IF;
        END $$;
        """
    )
