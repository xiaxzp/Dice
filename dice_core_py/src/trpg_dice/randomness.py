from __future__ import annotations

import random
import secrets
from collections.abc import Iterable
from typing import Protocol


class RandomSource(Protocol):
    def randint(self, lower: int, upper: int) -> int:
        """Return an integer in the inclusive interval [lower, upper]."""


class SystemRandomSource:
    """Production random source backed by the operating system."""

    def __init__(self) -> None:
        self._random = secrets.SystemRandom()

    def randint(self, lower: int, upper: int) -> int:
        return self._random.randint(lower, upper)


class SeededRandomSource:
    """Reproducible random source for simulations and debugging."""

    def __init__(self, seed: int | str | bytes | bytearray | None = None) -> None:
        self._random = random.Random(seed)

    def randint(self, lower: int, upper: int) -> int:
        return self._random.randint(lower, upper)


class SequenceRandomSource:
    """Deterministic source that consumes a predefined sequence."""

    def __init__(self, values: Iterable[int]) -> None:
        self._values = iter(values)

    def randint(self, lower: int, upper: int) -> int:
        try:
            value = next(self._values)
        except StopIteration as error:
            raise RuntimeError("deterministic random sequence is exhausted") from error
        if not lower <= value <= upper:
            raise ValueError(
                f"deterministic value {value} is outside [{lower}, {upper}]"
            )
        return value
