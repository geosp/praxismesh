"""Error types shared across PraxisMesh. The Temporal retry policy treats every
`NonRetryableError` as final (RFC: Phase 1, TaskWorkflow)."""

from __future__ import annotations


class PraxisError(Exception):
    """Base class for PraxisMesh errors."""


class NonRetryableError(PraxisError):
    """A failure that retrying cannot fix."""


class CapabilityError(NonRetryableError):
    """A profile, request or template asks for a capability it may not have."""


class InvalidTaskInput(NonRetryableError):
    """A task request is malformed."""


class TaskAlreadyExists(NonRetryableError):
    """A task ID was used by an earlier run."""


class BudgetExceeded(NonRetryableError):
    """A task has used up a turn, token or wall-time budget."""


class RegistryError(PraxisError):
    """Registry files are invalid or out of step with `registry/registry.lock`."""


class TemplateVersionUnavailable(PraxisError):
    """This worker runs a different template version than the task; retryable."""
