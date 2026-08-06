"""The hierarchy's vocabulary: what a node can be, and who can see it.

Plain enums with no ORM or framework dependency, which is why they live in
`domain/` rather than beside the table that stores them. They were in
`infra/models.py`, and every consumer that wanted only the vocabulary — schemas,
the access rules, the routes — had to import the ORM module to get it. That made
`domain -> infra` look mandatory when it never was.

`Node` itself stays in `infra/`: it is a `SQLModel` table and cannot be anything
else.
"""

from enum import Enum


class NodeType(str, Enum):
    """A single `nodes` table models all three via this discriminator.

    REFERENCE is the one that is not a container: it points at another node, which
    is what lets a deck appear in more than one place without being copied.
    """

    FOLDER = "FOLDER"
    DECK = "DECK"
    REFERENCE = "REFERENCE"


class Visibility(str, Enum):
    """Direct visibility. Inherited readability is a separate, computed question.

    A PRIVATE node can still be readable — through a PUBLIC folder above it, along
    same-owner edges. `application/access.py` decides that; this only records what
    was set on the node itself.
    """

    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"
