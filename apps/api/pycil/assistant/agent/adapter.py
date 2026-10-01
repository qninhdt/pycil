"""The AG-UI adapter, configured for Pycil's durability and context contract.

`ag-ui-langgraph` owns the AG-UI event protocol, so this module adds only the two
things Pycil needs on top of it:

* **Exit-only checkpointing.** The adapter never sets ``durability``, so LangGraph
  applies its default and writes a checkpoint at every super-step. The accepted
  behavior is one checkpoint at exit or at an approval interrupt, so the kwarg is
  injected into the stream call.
* **A typed request context.** The adapter flattens the context it passes to the
  graph into a plain dict, which would turn the actor's ``UUID`` into a ``str``
  and break every tool that compares it against an owner column. The typed
  ``AssistantContext`` is injected whole instead.

Both are injected through ``get_stream_kwargs``, which is the adapter's own
extension point: the alternative is rebuilding the event protocol, which is the
work this phase exists to delete.
"""

from typing import Any
from uuid import UUID

from ag_ui_langgraph import LangGraphAgent

from pycil.assistant.agent.context import AssistantContext

#: One checkpoint at exit, or at an approval interrupt. Intermediate tool steps
#: write nothing, which is what bounds checkpoint growth on a long turn.
DURABILITY = "exit"


def checkpoint_thread_id(owner_id: UUID, thread_id: UUID) -> str:
    """The checkpointer key for one learner's thread.

    Namespaced by owner because the adapter takes the checkpoint key straight
    from the request. Naming is not authorization — the router verifies
    `AssistantThread.owner_id` before this is used — but it does mean a guessed
    or replayed thread id cannot collide with another learner's history.
    """
    return f"assistant:{owner_id}:{thread_id}"


class PycilAgent(LangGraphAgent):
    """The maintained adapter with Pycil's durability and context contract."""

    #: Set per request by the router. Held on the instance rather than passed
    #: through the AG-UI input because the actor's identity must come from the
    #: verified bearer, never from a client-supplied field.
    request_context: AssistantContext | None = None

    def get_stream_kwargs(self, *args: Any, **kwargs: Any) -> dict:
        # `durability` is not an adapter parameter, so it cannot be forwarded
        # through the call. It is added to the kwargs the parent returns, which
        # astream_events passes through to astream and its checkpointer.
        kwargs.pop("durability", None)
        stream_kwargs = super().get_stream_kwargs(*args, **kwargs)
        stream_kwargs["durability"] = DURABILITY
        if self.request_context is not None:
            stream_kwargs["context"] = self.request_context
            payload = stream_kwargs.get("input")
            if isinstance(payload, dict) and "messages" in payload:
                stream_kwargs["input"] = {
                    **payload,
                    "selected_model_id": self.request_context.model_id,
                    "selected_effort": self.request_context.reasoning_effort,
                }
        self._namespace_checkpoint_config(stream_kwargs)
        return stream_kwargs

    def _namespace_checkpoint_config(self, stream_kwargs: dict) -> None:
        """Point the checkpointer at the owner-namespaced key.

        The adapter keys its checkpoint by ``input.thread_id`` verbatim, which is the
        client's own value. Every read in the product — thread state, resume, deletion
        — goes through :func:`checkpoint_thread_id`, so without this the write and the
        read address two different rows and the conversation appears empty: a paused
        turn reports no interrupt, resume cannot find the state it is continuing, and
        deleting a thread leaves its history behind.

        The rewrite is applied to the checkpointer's config and never to the request,
        so the id echoed back to the client stays the one it sent. Naming is not
        authorization — the router verifies thread ownership before any of this runs —
        but it does mean a guessed id cannot address another learner's history.
        """
        config = stream_kwargs.get("config")
        if not isinstance(config, dict):
            return
        configurable = config.get("configurable")
        if not isinstance(configurable, dict):
            return
        thread_id = configurable.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            return
        owner_id = getattr(self.request_context, "user_id", None)
        if not isinstance(owner_id, UUID):
            return
        try:
            namespaced = checkpoint_thread_id(owner_id, UUID(thread_id))
        except ValueError:
            # A malformed id is the router's to reject, not this seam's; leaving the
            # config untouched keeps the failure where it belongs.
            return
        configurable["thread_id"] = namespaced
