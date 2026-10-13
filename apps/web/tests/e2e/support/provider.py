"""Controlled HTTP provider; Instructor, agent tools and persistence stay real."""

import asyncio
import json
import re
from collections import Counter
from uuid import uuid4

from data import payloads
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
failed = Counter()


@app.get("/health")
async def health():
    return {"ok": True}


def tagged(content, tag):
    return json.loads(re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", content, re.DOTALL).group(1))


def generation(body):
    messages = body["messages"]
    user = next(m["content"] for m in messages if m["role"] == "user")
    name = body["response_format"]["json_schema"]["name"]
    if name == "GroundedInventory":
        data = tagged(user, "word_request")
        target = data["target"]
        if target == "quay" and failed["quay"] == 0:
            failed["quay"] += 1
            return None
        lemma = (
            "glisten with {sth}"
            if target.startswith("glisten with")
            else "glisten"
            if target.startswith("glisten")
            else target
        )
        pos, references = next(iter(data["references"].items()))
        source = references[0]
        return dict(
            lemma=lemma,
            type="phrasal_verb" if " " in lemma else "word",
            aliases=[],
            related=[],
            senses=[
                dict(
                    definition=source["definition"],
                    pos=pos if pos in {"noun", "verb", "adjective", "adverb"} else "noun",
                    references=[source["id"]],
                )
            ],
        )
    if name == "GroundedEnrichment":
        data = tagged(user, "sense_request")
        lemma = data["word"]["lemma"]
        target = lemma.removesuffix(" {sth}")
        slot_example = " water" if target != lemma else ""
        example = (
            f"Ships dock at the [{target}]."
            if lemma == "jetty"
            else f"They use [{target}]{slot_example} in everyday life."
        )
        return {
            "senses": [
                dict(
                    sense_id=s["sense_id"],
                    tier="core",
                    cefr_level="a2",
                    register=None,
                    examples=[example],
                    forms=[],
                    patterns=[],
                    collocations=[],
                    relations=[],
                )
                for s in data["senses"]
            ]
        }
    if name == "ArtifactBatch":
        data = tagged(user, "artifact_context")
        if (
            data["word"] == "bank"
            and data["definition"] == "an institution whose questions are initially unavailable"
            and failed["cold"] == 0
        ):
            failed["cold"] += 1
            return None
        schema = body["response_format"]["json_schema"]["schema"]
        ref = schema["properties"]["artifacts"]["items"]["$ref"].split("/")[-1]
        kinds = {
            "WordDefinitionArtifact": "word_definition",
            "UsageArtifact": "word_to_usage",
            "ContextWordMeaningArtifact": "context_word_meaning",
            "ContextToWordArtifact": "context_to_word",
            "DialogueArtifact": "dialogue_completion",
            "RewriteArtifact": "sentence_rewrite",
        }
        return {
            "artifacts": [
                payloads(data["word"], data["definition"], i)[kinds[ref]]
                for i in range(data.get("batch_size", 1))
            ]
        }
    raise ValueError(f"Unexpected response schema: {name}")


@app.post("/decisions")
async def decisions(request: Request):
    body = await request.json()
    state = body["state"]
    wrong = state.get("answer") == "unrelated"
    answers = {}
    for name, question in body["questions"].items():
        kind = question["type"]
        if kind == "choice":
            choices = question["criteria"]
            preferred = (
                "no_candidate"
                if wrong
                else {
                    "accuracy": "accurate",
                    "coverage": "sufficient",
                    "meaning": "correct",
                    "form": "correct",
                    "meaning_preservation": "preserved",
                }.get(name)
            )
            value = (
                preferred
                if preferred in choices
                else next((k for k in choices if k != "no_candidate"), next(iter(choices)))
            )
        else:
            value = 0 if wrong or name == "spelling_error" else 1
        answers[name] = {"type": kind, kind: value}
    return {"answers": answers}


@app.post("/chat/completions")
async def completions(request: Request):
    body = await request.json()
    if "response_format" in body:
        output = generation(body)
        message = (
            {"role": "assistant", "content": json.dumps(output)}
            if output is not None
            else {
                "role": "assistant",
                "content": None,
                "refusal": "Controlled provider rejection",
            }
        )
        return {
            "id": "chatcmpl-" + uuid4().hex,
            "object": "chat.completion",
            "created": 1,
            "model": body["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        }
    messages = body["messages"]
    # Context follows the user message; select the test command rather than the view data.
    content = next(
        (
            m["content"]
            for m in reversed(messages)
            if m["role"] == "user"
            and isinstance(m["content"], str)
            and m["content"].startswith("E2E")
        ),
        "E2E hello",
    )
    if content == "E2E fail":
        return JSONResponse(
            {
                "error": {
                    "message": "Controlled provider failure",
                    "type": "invalid_request_error",
                }
            },
            status_code=400,
        )
    human_index = max(i for i, m in enumerate(messages) if m["role"] == "user")
    tool_results = [m for m in messages[human_index + 1 :] if m["role"] == "tool"]
    call = None
    if not tool_results:
        if content.startswith("E2E read node "):
            call = (
                "read_library",
                {"node_id": content.removeprefix("E2E read node "), "view": "content"},
            )
        elif content.startswith("E2E create deck "):
            call = (
                "create_node",
                {
                    "type": "deck",
                    "name": content.removeprefix("E2E create deck "),
                    "sense_ids": [],
                },
            )
        elif content == "E2E missing sense":
            call = ("read_vocabulary", {"sense_ids": [2147483647]})
    answer = "E2E response saved through the native checkpoint."
    if tool_results:
        answer = (
            "E2E recovered from a missing sense."
            if content == "E2E missing sense"
            else tool_results[-1]["content"]
        )

    async def stream():
        identifier = "chatcmpl-" + uuid4().hex

        def chunk(delta, finish=None, usage=None):
            value = {
                "id": identifier,
                "object": "chat.completion.chunk",
                "created": 1,
                "model": body["model"],
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            if usage:
                value["usage"] = usage
            return "data: " + json.dumps(value) + "\n\n"

        yield chunk({"role": "assistant"})
        if content == "E2E slow":
            await asyncio.sleep(30)
        if call:
            name, arguments = call
            yield chunk(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_" + uuid4().hex,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ]
                }
            )
        elif content == "E2E streaming across timeouts":
            yield chunk({"reasoning": "E2E reasoning arrives before the answer."})
            await asyncio.sleep(2)
            yield chunk({"content": "E2E first paragraph.\n\n"})
            await asyncio.sleep(16)
            yield chunk({"content": "A long continuation. " * 120})
            await asyncio.sleep(16)
            yield chunk({"content": "\n\nE2E final paragraph."})
        else:
            yield chunk({"content": answer})
        yield chunk(
            {},
            "tool_calls" if call else "stop",
            {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
