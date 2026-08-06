"""Orchestration for hierarchy: use cases that need a session but are not routes.

This is where reads and writes both live, so a read cannot quietly bypass the
layer a write goes through. Routes call in here; nothing here knows about HTTP.
"""
