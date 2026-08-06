"""Learning persistence: the ORM tables and the Redis session store.

`session_store.py` is the ephemeral tier (Redis) and `models.py` the durable one
(Postgres). Both are storage, so both sit here; the FSRS decisions that use them
live in `application/`.
"""
