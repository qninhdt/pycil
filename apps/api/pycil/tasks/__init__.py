"""Durable, generic async-task orchestration primitives.

This package is intentionally transport-free. Producers authorize requests and
derive work keys before calling the service; the worker relays persisted outbox
snapshots separately.
"""
