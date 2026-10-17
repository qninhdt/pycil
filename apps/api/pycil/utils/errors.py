"""Operation failures independent of HTTP, worker transport or presentation."""


class OperationError(Exception):
    def __init__(self, code: str, *, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(code)


class NotFound(OperationError):
    pass


class InvalidInput(OperationError):
    pass


class Conflict(OperationError):
    pass


class Forbidden(OperationError):
    pass


class Unavailable(OperationError):
    pass


class RateLimited(OperationError):
    pass


class InputTooLarge(OperationError):
    pass


class Unauthenticated(OperationError):
    pass
