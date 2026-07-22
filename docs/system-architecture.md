# System Architecture

See [current-system-architecture.md](./current-system-architecture.md) for the
canonical deployment. Pycil embeds the GitHub-pinned `lexi_ai` as a pure domain library;
Lexi owns the isolated `lexi` schema in the shared Postgres cluster. Pycil owns
the application schema, task outbox, worker orchestration, and SSE delivery.

The API and worker create separate Lexi pools. Compose applies Lexi's domain
migrations before Pycil's migrations. No Lexi HTTP/gRPC process, service
deployment, service secrets, status polling, or WebSocket client path remains.
