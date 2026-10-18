from types import TracebackType
from typing import Self

from pycil.infrastructure.llm import TokenUsage, merge_usage, records
from pycil.vocabulary.generation.schemas import EnrichmentBatch, Inventory


class UsageRecorder:
    def __enter__(self) -> Self:
        self.records: list[TokenUsage] = []
        self.token = records.set(self.records)
        return self

    def __exit__(
        self,
        _kind: type[BaseException] | None,
        error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        records.reset(self.token)
        if error is not None:
            setattr(error, "usage", merge_usage(self.records))  # noqa: B010

    def finish[T](self, value: T) -> tuple[T, list[TokenUsage]]:
        return value, merge_usage(self.records)


class WordProvider:
    def __init__(self, *, invalid_citation=False):
        self.calls = 0
        self.invalid_citation = invalid_citation

    async def complete(self, instruction, data, schema):
        self.calls += 1
        if issubclass(schema, Inventory):
            return schema.model_validate(
                dict(
                    lemma="bank",
                    type="word",
                    aliases=[],
                    related=[dict(type="word_family", lemmas=["banking"])],
                    senses=[
                        dict(
                            definition="a financial institution",
                            pos="noun",
                            references=["a999" if self.invalid_citation else "a1"],
                        )
                    ],
                )
            )
        if issubclass(schema, EnrichmentBatch):
            return schema.model_validate(
                dict(
                    senses=[
                        dict(
                            sense_id=1,
                            tier="common",
                            cefr_level="a2",
                            register=None,
                            examples=["The [bank] opens at nine."],
                            forms=["bank", "banks|pl"],
                            patterns=[],
                            collocations=["bank account"],
                            relations=[dict(type="synonym", lemmas=["lender"])],
                        )
                    ]
                )
            )
        raise AssertionError("unexpected provider operation")
