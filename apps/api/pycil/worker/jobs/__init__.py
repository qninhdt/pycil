"""Content jobs and the retention sweep.

`reconcile_assistant_retention` is deliberately **not** in the worker's handler
registry: the registry holds the kinds the API publishes, and nothing publishes a
retention job. It is invoked as an operator action.
"""
