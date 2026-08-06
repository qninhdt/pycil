"""Work-key builders for generic async tasks.

A work key is the server-derived identity two callers must agree on to join the
same task rather than each starting a duplicate. Never accepted from a client —
`submit_or_join` takes the key, so a caller able to choose it could join somebody
else's task.

Held down to the kinds that exist. Three further builders — an HMAC helper plus
translation and TTS keys — were written ahead of features that never shipped and
were referenced by nothing. Speculative keys are worse than absent ones: the next
reader takes them for a contract something already depends on.
"""


def word_work_key(match_key: str, dataset_fingerprint: str) -> str:
    return f"word:{match_key}:{dataset_fingerprint}"


def grading_work_key(response_id: str) -> str:
    return f"grading:{response_id}"


def supply_work_key(session_id: str, round_index: int) -> str:
    """Identity of one session's supply request for one round.

    Keyed by session and round rather than by the demands themselves. The demand
    list is derived from whatever the round still has unresolved, so two `/next`
    calls landing in the same round can compute *different* lists — the first
    consumes a delivery the second no longer sees. Keying on the list would make
    those two distinct tasks, and the learner would be charged twice for the same
    round's generation while the client subscribed to whichever id it saw last.

    Not keyed by owner: `session_id` is already a per-learner opaque id, and
    `submit_or_join` scopes the interest to the requester regardless.
    """
    return f"supply:{session_id}:{round_index}"
