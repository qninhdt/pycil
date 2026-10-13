from pydantic import BaseModel, ConfigDict, Field, field_validator


class ThemeParts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voice: str = Field(min_length=1, max_length=1000)
    diction: str = Field(min_length=1, max_length=1000)

    @field_validator("voice", "diction")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("theme descriptor must not be blank")
        return value


class Theme(ThemeParts):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: int
    key: str
    name: str
