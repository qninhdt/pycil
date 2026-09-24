"""Lexi's content-hash unique key makes a repeated supply write idempotent.

Supply preparation can be redelivered: at-least-once delivery means a worker that
commits and then crashes is asked to run the same job again. The guarantee that
makes this safe is Lexi's, not Pycil's — the same question content written twice
produces one row — so this pins the installed library's contract rather than
reimplementing it.
"""

from lexi_ai.domain.questions import PersistedQuestion, RenderKind
from lexi_ai.infrastructure.db.models import Question
from lexi_ai.infrastructure.db.repositories.question_repo import QuestionRepository
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def test_repeated_supply_write_has_one_canonical_content_row():
    import os

    url = os.environ.get("TEST_DB_URL")
    if not url:
        import pytest

        pytest.skip("TEST_DB_URL is required for the Lexi integration check")

    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            repo = QuestionRepository(session)
            question = PersistedQuestion(
                word_id=1,
                sense_id=1,
                difficulty_level=1,
                render_kind=RenderKind.cloze,
                content_hash="fixed-content-hash",
                payload={"prompt": "a fixed prompt"},
            )
            await repo.upsert(question)
            await repo.upsert(question)
            await session.commit()

            count = await session.scalar(
                select(func.count()).select_from(Question).where(
                    Question.content_hash == "fixed-content-hash"
                )
            )
            assert count == 1
    finally:
        await engine.dispose()
