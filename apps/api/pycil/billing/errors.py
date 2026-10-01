"""Billing and entitlement domain exceptions."""

from pycil.platform.errors import ConflictError, ForbiddenError


class BillingInvariantError(Exception):
    """Raised when an internal billing or settlement invariant is violated."""


class UsageQuotaExhaustedError(ConflictError):
    """Raised at admission when an operation has exhausted its usage quota."""

    def __init__(self, message: str = "usage_quota_exhausted") -> None:
        super().__init__(message, code="usage_quota_exhausted")


class InsufficientAllowanceError(ConflictError):
    """Raised when known fixed cost exceeds remaining usage allowance."""

    def __init__(self, message: str = "insufficient_allowance") -> None:
        super().__init__(message, code="insufficient_allowance")


class FeatureNotAvailableError(ForbiddenError):
    """Raised when an account plan does not entitle access to a feature."""

    def __init__(self, message: str = "feature_not_available") -> None:
        super().__init__(message, code="feature_not_available")
