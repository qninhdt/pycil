"""Outbound ports: narrow seams onto things outside this service.

A port here is dependency-free by construction — it may import stdlib, a client
library, and `pycil.config`, and nothing else from `pycil`. That is what lets any
domain import one without creating an edge back into another domain.

These modules did not move because a layer diagram asked for it. Each was already
a leaf that two or more domains reached across a boundary to use, which is what
turned four thin edges into import cycles:

* `lexi` (was `content/lexi_port.py`) — a `Protocol`. `hierarchy` and `learning`
  imported it from `content`, which is most of what `-> content` meant.

Nothing in this package may import a domain. `check-module-cycles.py` and the
import-linter contract both enforce that.
"""
