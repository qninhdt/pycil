"""Persistence for tasks: ORM tables and the adapters that back them.

The only layer permitted to define a `SQLModel` table. Kept separate so `domain/`
stays importable without a database.
"""
