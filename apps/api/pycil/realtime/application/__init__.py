"""Orchestration for realtime: use cases that need a session but are not routes.

Reads and writes both live here, so a read cannot quietly bypass the layer a
write goes through. Routes call in; nothing here knows about HTTP.
"""
