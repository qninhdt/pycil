"""Pure types and rules for tasks: no session, no HTTP, no ORM.

Importable from any layer without pulling in a database or a request. If
something here needs a session, it belongs in `application/`.
"""
