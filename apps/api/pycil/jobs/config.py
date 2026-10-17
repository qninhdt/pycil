from typing import Self

from pydantic import model_validator

from pycil.utils.configuration import Policy, PositiveInt


class JobsConfig(Policy):
    timeout_seconds: PositiveInt = 300
    lock_timeout_seconds: PositiveInt = 330
    result_ttl_seconds: PositiveInt = 86400

    @model_validator(mode="after")
    def deadlines(self) -> Self:
        if self.lock_timeout_seconds <= self.timeout_seconds:
            raise ValueError("job lock expiry must exceed execution timeout")
        return self


