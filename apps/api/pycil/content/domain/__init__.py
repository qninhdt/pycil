"""Pure types and rules for content: no session, no HTTP, no ORM.

What lives here can be imported by any layer without dragging in a database or a
request. That is the whole constraint — if something here needs a session, it
belongs in `application/`.
"""
