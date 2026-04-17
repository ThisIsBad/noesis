"""Domain-specific exception hierarchy for LogicBrain.

All exceptions inherit from ``LogicBrainError``.  Where an exception
replaces a previously-raised ``ValueError``, it additionally inherits
from ``ValueError`` so that existing ``except ValueError`` handlers
continue to work.
"""

from __future__ import annotations


class LogicBrainError(Exception):
    """Base exception for all LogicBrain errors."""


class VerificationError(LogicBrainError, ValueError):
    """Raised when a verification operation fails."""


class ConstraintError(LogicBrainError, ValueError):
    """Raised when a Z3 constraint is invalid or cannot be parsed."""


class SessionError(LogicBrainError):
    """Base for session-management failures."""


class CertificateError(LogicBrainError, ValueError):
    """Raised for certificate creation or store failures."""


class PolicyViolationError(LogicBrainError, ValueError):
    """Raised when a policy evaluation encounters an error."""
