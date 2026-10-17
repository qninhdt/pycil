from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from pycil.app.schema import register_models, verify_schema
from pycil.infrastructure.database import Base


async def test_initial_migration_matches_application_metadata(database):
    register_models()

    def differences(connection):
        context = MigrationContext.configure(
            connection,
            opts={
                "compare_type": True,
                "include_object": lambda obj, name, kind, reflected, compared: (
                    kind != "table" or name in Base.metadata.tables
                ),
            },
        )
        return compare_metadata(context, Base.metadata)

    async with database.engine.connect() as connection:
        assert await connection.run_sync(differences) == []
    await verify_schema(database.engine, require_reference=False)
