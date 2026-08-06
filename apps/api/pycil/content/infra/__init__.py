"""Persistence for content: ORM tables and the caches that back them.

The only layer permitted to define a `SQLModel` table or talk to Redis. Kept
separate so `domain/` stays importable without a database.
"""
