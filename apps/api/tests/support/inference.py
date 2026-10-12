"""Controlled inference boundaries shared by backend and browser tests."""

import asyncio
import json
import re
from types import SimpleNamespace
from uuid import uuid4

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field
from typesafe_sdk import Choice


class Completion(BaseChatModel):
    responses: list[AIMessage] = Field(default_factory=list)
    calls: int = 0
    delay: float = 0

    @property
    def _llm_type(self):
        return "deterministic-external-completion"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.delay:
            await asyncio.sleep(self.delay)
        return self._generate(messages)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        if self.delay:
            await asyncio.sleep(self.delay)
        response = self._generate(messages).generations[0].message
        yield ChatGenerationChunk(message=AIMessageChunk(**response.model_dump(exclude={"type"})))


def answer(content="Hello", **kwargs):
    return AIMessage(
        content=content,
        usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        **kwargs,
    )


class LocalCompletion:
    """Deterministic inference boundary; native generation and storage remain real."""

    def __init__(self):
        self.calls = 0

    async def complete(self, instruction, data, schema):
        self.calls += 1
        c = json.loads(data.removeprefix("<artifact_context>").removesuffix("</artifact_context>"))
        word, definition = c["word"], c["definition"]
        model = schema.model_fields["artifacts"].annotation.__args__[0].__name__
        output = []
        for i in range(c.get("batch_size", 1)):
            wrong = [f"other{self.calls}_{i}_{j}" for j in range(c["distractor_count"])]
            if model == "WordDefinitionArtifact":
                payload = dict(
                    corrects=[
                        f"Paraphrase {self.calls}_{j}: {definition}"
                        for j in range(c["correct_count"])
                    ],
                    distractors=[dict(word=w, definition=f"another meaning {w}") for w in wrong],
                )
            elif model == "UsageArtifact":
                payload = dict(
                    corrects=[
                        f"The [{word}] is useful here ({self.calls}_{j})."
                        for j in range(c["correct_count"])
                    ],
                    distractors=[f"The [{word}] grows {w}." for w in wrong],
                )
            elif model == "ContextToWordArtifact":
                payload = dict(
                    context=f"Customer {self.calls}-{i} needed somewhere to deposit savings.",
                    distractors=wrong,
                )
            elif model == "ContextWordMeaningArtifact":
                payload = dict(
                    context=f"They visited the _ ({self.calls}-{i}).",
                    correct=dict(expression=word, meaning=definition),
                    distractors=[dict(expression=w, meaning=f"meaning of {w}") for w in wrong],
                )
            elif model == "DialogueArtifact":
                payload = dict(
                    conversation=[
                        {"Alex": f"Can I deposit savings here ({self.calls}_{i})?"},
                        {"Jamie": f"Yes, this is a [{word}]."},
                        {"Alex": "Can I open an account?"},
                        {"Jamie": "Bring identification."},
                    ],
                    completion_points=[dict(turn_index=2, distractors=wrong)],
                )
            else:
                payload = dict(
                    source=f"They put money in an institution ({self.calls}_{i}).",
                    correct=f"They deposited money at the [{word}].",
                    distractors=[f"The [{word}] grows {w}." for w in wrong],
                )
            output.append(payload)
        return dict(artifacts=output)


class BrowserLexicalCompletion(LocalCompletion):
    failed_once = False

    question_failure = False

    async def complete(self, instruction, data, schema):
        if schema.__name__ == "ArtifactBatch" and self.question_failure:
            context = json.loads(re.sub(r"</?\w+>", "", data).strip())
            if context["definition"].endswith("fixture meaning 32"):
                from openai import BadRequestError

                self.question_failure = False
                request = httpx.Request("POST", "https://provider.invalid/completions")
                raise BadRequestError(
                    "deterministic provider rejection",
                    response=httpx.Response(400, request=request),
                    body=None,
                )
        if schema.__name__ not in {"InventoryOutput", "EnrichmentBatch"}:
            return await super().complete(instruction, data, schema)
        context = json.loads(re.sub(r"</?\w+>", "", data).strip())
        target = (
            context["target"] if schema.__name__ == "InventoryOutput" else context["word"]["lemma"]
        )
        if schema.__name__ == "InventoryOutput":
            if target == "quay" and not self.failed_once:
                self.failed_once = True
                raise ValueError("deterministic provider failure")
            return {
                "lemma": (
                    "glisten with {sth}"
                    if target == "glisten with something"
                    else "glisten"
                    if target in {"glistening", "glistened"}
                    else target
                ),
                "type": "PHRASAL_VERB" if target == "glisten with something" else "WORD",
                "aliases": [],
                "related": {},
                "senses": [
                    {
                        "definition": next(iter(context["references"].values()))[0]["definition"],
                        "pos": next(iter(context["references"])),
                        "references": ["a1"],
                    }
                ],
            }
        if target == "jetty":
            examples = [
                "Ships dock at the [jetty].",
                "SHIPS DOCK AT THE [JETTY].",
                "[jetty",
            ]
        else:
            examples = [
                f"The ship entered the [{target}] today ({n})."
                for n in range(context["examples_per_sense"])
            ]
        return {
            "senses": [
                {
                    "sense_id": sense["sense_id"],
                    "tier": "core",
                    "examples": examples,
                    "forms": [target],
                    "patterns": [],
                    "collocations": [],
                    "relations": {},
                    "cefr_level": "B1",
                    "register": None,
                }
                for sense in context["senses"]
            ]
        }


class BrowserCompletion(Completion):
    """Only the inference boundary is deterministic; native agents/tools stay real."""

    @staticmethod
    def last_message(messages):
        return next(
            m
            for m in reversed(messages)
            if not (
                m.type == "human"
                and isinstance(m.content, str)
                and m.content.startswith("<context>")
            )
        )

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        last = self.last_message(messages)
        content = last.content if isinstance(last.content, str) else "E2E vision"
        if "E2E fail" in content:
            raise RuntimeError("deterministic provider failure")
        if not isinstance(last, ToolMessage) and content == "E2E missing sense":
            result = answer(
                "",
                tool_calls=[
                    {
                        "name": "read_vocabulary",
                        "args": {"sense_ids": [999999]},
                        "id": "call_" + uuid4().hex,
                    }
                ],
            )
        elif isinstance(last, ToolMessage) and last.name == "read_vocabulary":
            assert last.status == "error" and last.content == "sense_not_found"
            result = answer("E2E recovered from a missing sense.")
        elif not isinstance(last, ToolMessage) and content.startswith("E2E create deck "):
            result = answer(
                "",
                tool_calls=[
                    {
                        "name": "create_node",
                        "args": {"type": "DECK", "name": content[16:]},
                        "id": "call_" + uuid4().hex,
                    }
                ],
            )
        elif not isinstance(last, ToolMessage) and content.startswith("E2E read node "):
            result = answer(
                "",
                tool_calls=[
                    {
                        "name": "read_library",
                        "args": {"node_id": content[14:]},
                        "id": "call_" + uuid4().hex,
                    }
                ],
            )
        elif isinstance(last, ToolMessage) and last.name == "read_library":
            result = answer("E2E tool result: " + str(last.content))
        else:
            result = answer("E2E response saved through the native checkpoint.")
        return self._result(result)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        if self.last_message(messages).content == "E2E streaming across timeouts":
            from langchain_core.messages import AIMessageChunk
            from langchain_core.outputs import ChatGenerationChunk

            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[
                        {
                            "type": "reasoning",
                            "reasoning": "E2E reasoning arrives before the answer.",
                            "index": 0,
                        }
                    ]
                )
            )
            await asyncio.sleep(3)
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[{"type": "text", "text": "E2E first paragraph. ", "index": 1}]
                )
            )
            await asyncio.sleep(32)
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[{"type": "text", "text": "A long continuation. " * 200, "index": 1}]
                )
            )
            await asyncio.sleep(32)
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[{"type": "text", "text": "E2E final paragraph.", "index": 1}],
                    usage_metadata={
                        "input_tokens": 10,
                        "output_tokens": 1000,
                        "total_tokens": 1010,
                    },
                )
            )
            return
        if self.last_message(messages).content == "E2E slow":
            await asyncio.sleep(3)
        async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
            yield chunk

    def _result(self, message: AIMessage):
        from langchain_core.outputs import ChatGeneration, ChatResult

        return ChatResult(generations=[ChatGeneration(message=message)])


class DiagnosticProvider:
    async def decide(self, state, questions, **options):
        return SimpleNamespace(
            choices={
                name: SimpleNamespace(choice="no_candidate")
                for name, question in questions.items()
                if isinstance(question, Choice)
            },
            nouls={
                name: SimpleNamespace(noul=0.1)
                for name in questions
                if name in {"task_fit", "spelling_error", "used"}
            },
        )

    async def close(self):
        pass
