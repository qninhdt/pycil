"""Real separate-process search owner/reader for the shared-directory contract."""

import asyncio
import time

from pycil.app.config import load_config
from pycil.app.schema import register_models
from pycil.infrastructure.database import connect
from pycil.vocabulary.search import SearchIndex


def run(connection, url, directory, policy, crash_control=None):
    async def serve():
        register_models()
        engine, sessions = connect(url)
        index = SearchIndex(
            sessions, directory, policy=policy, query_policy=load_config().vocabulary.search
        )
        if crash_control is not None:
            armed, reached, after_commit = crash_control
            commit = index._commit

            def controlled_commit(writer, cursor):
                if armed.is_set() and not after_commit:
                    reached.set()
                    time.sleep(20)
                commit(writer, cursor)
                if armed.is_set() and after_commit:
                    reached.set()
                    time.sleep(20)

            index._commit = controlled_commit
        applications = 0
        synchronize = index.synchronize

        async def count_batch(writer):
            nonlocal applications
            changed = await synchronize(writer)
            applications += int(changed)
            return changed

        index.synchronize = count_batch
        try:
            await index.start()
            connection.send({"ready": True})
            while True:
                command = await asyncio.to_thread(connection.recv)
                if command[0] == "stop":
                    return
                if command[0] == "wait":
                    await index.wait_for_revision(command[1])
                hits = (await index.search(command[2])).items if len(command) > 2 else []
                connection.send(
                    {
                        "owner": index.is_owner,
                        "cursor": index.cursor(),
                        "applications": applications,
                        "words": [hit.word_id for hit in hits],
                    }
                )
        except Exception as error:
            connection.send({"error": repr(error)})
            raise
        finally:
            await index.close()
            await engine.dispose()
            connection.close()

    asyncio.run(serve())
