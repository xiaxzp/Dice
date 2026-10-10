class DiceError(Exception):
    """Base class for errors returned by the standalone dice module."""


class DiceExpressionError(DiceError, ValueError):
    """The dice expression is invalid or exceeds configured limits."""


class DiceLimitError(DiceExpressionError):
    """A dice expression exceeds a safety limit."""


class DivisionByZeroError(DiceExpressionError, ZeroDivisionError):
    """A dice expression attempted integer division by zero."""


class IdentityError(DiceError):
    """An actor, source, nickname, or character operation is invalid."""


class NotFoundError(IdentityError, LookupError):
    """A requested profile or character card does not exist."""


class ConflictError(IdentityError):
    """An identity object conflicts with an existing object."""


class StorageError(DiceError):
    """Persistent JSON data could not be safely loaded or saved."""


class CommandError(DiceError, ValueError):
    """A command is malformed or cannot be executed."""


class UnknownCommandError(CommandError):
    """The command router does not have a handler for the requested command."""
