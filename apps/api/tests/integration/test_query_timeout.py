import httpx
from sqlalchemy import text

from pycil.dependencies import Session
from pycil.main import create_app


async def test_statement_timeout_is_retryable_and_request_transaction_is_discarded(
    database, config
):
    _, sessions, _ = database
    app = create_app()
    app.state.sessions, app.state.product = sessions, config

    @app.get("/timeout-test")
    async def timeout(session: Session):
        await session.execute(text("SET LOCAL statement_timeout = '20ms'"))
        await session.execute(text("SELECT pg_sleep(0.2)"))

    @app.get("/query-test")
    async def query(session: Session):
        return {"value": await session.scalar(text("SELECT 1"))}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/timeout-test")
        assert response.status_code == 503
        assert response.json() == {"error": "query_timeout"}
        assert (await client.get("/query-test")).json() == {"value": 1}
