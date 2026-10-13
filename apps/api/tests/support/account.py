from uuid import uuid4

from pycil.account.models import User
from pycil.library.tree import provision_library


async def account(sessions, *, settings=None):
    async with sessions() as session, session.begin():
        user = User(clerk_subject="test_" + uuid4().hex, settings=settings or {})
        session.add(user)
        await session.flush()
        roots = await provision_library(session, user.id)
        return user, roots
