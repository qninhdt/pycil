"""Selected reference identities; runtime access is PostgreSQL only."""

import binascii

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.utils.encoding import base64url_decode, base64url_encode
from pycil.vocabulary.errors import InvalidHandleError
from pycil.vocabulary.references.models import ReferenceSense, ReferenceWord
from pycil.vocabulary.references.schemas import SourceSense, SourceWord


def encode_reference_id(identifier: int) -> str:
    if type(identifier) is not int or not 0 < identifier <= 2147483647:
        raise InvalidHandleError("invalid reference identity")
    return "entry_" + base64url_encode(f"entry:{identifier}".encode())


def decode_reference_id(value: str) -> int:
    if not value.startswith("entry_") or len(value) > 64:
        raise InvalidHandleError("invalid reference handle")
    try:
        token = value[6:]
        decoded = base64url_decode(token).decode("ascii")
        kind, number = decoded.split(":")
        identifier = int(number)
        if kind != "entry" or encode_reference_id(identifier) != value:
            raise ValueError("noncanonical reference handle")
        return identifier
    except (ValueError, UnicodeError, binascii.Error):
        raise InvalidHandleError("invalid reference handle") from None


async def fetch_reference(
    sessions: async_sessionmaker[AsyncSession], reference_id: str
) -> SourceWord:
    identifier = decode_reference_id(reference_id)
    async with sessions() as session:
        word = await session.get(ReferenceWord, identifier)
        if word is None:
            raise InvalidHandleError("reference word not found")
        senses = list(
            (
                await session.scalars(
                    select(ReferenceSense)
                    .where(ReferenceSense.word_id == identifier)
                    .order_by(
                        ReferenceSense.entry_order, ReferenceSense.sense_order, ReferenceSense.id
                    )
                )
            ).all()
        )
        if not senses:
            raise InvalidHandleError("reference word has no evidence")
        return SourceWord(
            id=word.id,
            lemma=word.lemma,
            display_form=word.display_form,
            entry_type=word.entry_type,
            alternatives=[(item[0], item[1]) for item in word.alternatives],
            inflections=list(word.inflections),
            senses=[
                SourceSense(**{name: getattr(sense, name) for name in SourceSense.model_fields})
                for sense in senses
            ],
        )
