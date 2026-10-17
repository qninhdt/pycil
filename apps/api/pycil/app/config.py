"""Module-centric configuration aggregation; credentials remain deployment-owned."""

import os
from pathlib import Path
from typing import Self

import yaml
from pydantic import ValidationError, model_validator

from pycil.account.config import AccountConfig
from pycil.assistant.config import AssistantConfig
from pycil.infrastructure.config import SystemConfig
from pycil.jobs.config import JobsConfig
from pycil.library.config import LibraryConfig
from pycil.study.config import StudyConfig
from pycil.study.enums import ResponseFormat
from pycil.utils.configuration import Policy
from pycil.vocabulary.config import VocabularyConfig


class AppConfig(Policy):
    account: AccountConfig
    vocabulary: VocabularyConfig
    library: LibraryConfig
    study: StudyConfig
    assistant: AssistantConfig
    jobs: JobsConfig
    system: SystemConfig

    @model_validator(mode="after")
    def validate_app_config(self) -> Self:
        if self.library.page_size > self.library.max_page_size:
            raise ValueError("default page size exceeds API read bound")
        if self.study.defaults.formats != [ResponseFormat.SINGLE_CHOICE]:
            raise ValueError("default learning preferences must work for Free")
        return self


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML duplicate keys are errors, never silent last-value-wins policy."""


def _mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key: object = loader.construct_object(key_node)  # pyright: ignore[reportUnknownMemberType]
        if key in result:
            raise ValueError(f"Duplicate config key: {key}")
        result[key] = loader.construct_object(value_node)  # pyright: ignore[reportUnknownMemberType]
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_config(path: Path | None = None) -> AppConfig:
    path = path or Path(
        os.environ.get("CONFIG_PATH", Path(__file__).resolve().parents[4] / "config/config.yaml")
    )
    try:
        data = yaml.load(path.read_text(), Loader=UniqueKeyLoader)
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(map(str, error["loc"])) or "root" for error in exc.errors()})
        raise ValueError("Invalid config at: " + ", ".join(fields)) from None
    except OSError, yaml.YAMLError:
        raise ValueError("Config is unreadable or malformed YAML") from None
