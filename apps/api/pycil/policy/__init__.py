"""Pure learning policy: the rules, with no I/O and no ORM.

`policy` holds the scheduling and admission rules; `history` derives a learner's
past from values already in hand. Neither opens a session, imports a model, or
reaches for a domain — they take plain arguments and return plain results, which
is the whole reason they can live here.

They were in `learning/`, where `content` and `hierarchy` imported them across a
boundary. That single import is what made `content -> learning` and
`hierarchy -> learning` edges, tangling three domains over code that depends on
none of them. Moving them costs nothing and removes both edges.

Nothing in this package may import a domain.
"""
