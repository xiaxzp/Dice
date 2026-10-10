from __future__ import annotations

import base64
import binascii
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .errors import DiceExpressionError, DiceLimitError
from .randomness import RandomSource, SystemRandomSource


@dataclass(slots=True)
class Roulette:
    """A no-replacement die that resets after all faces are consumed."""

    sides: int
    copies: int = 1
    rng: RandomSource = field(default_factory=SystemRandomSource)
    _pool: list[int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.sides <= 0 or self.copies <= 0:
            raise ValueError("roulette sides and copies must be positive")
        self.reset()

    @property
    def remaining(self) -> int:
        return len(self._pool)

    def reset(self) -> None:
        self._pool = [
            face for face in range(1, self.sides + 1) for _ in range(self.copies)
        ]

    def roll(self) -> int:
        if not self._pool:
            self.reset()
        index = self.rng.randint(0, len(self._pool) - 1)
        return self._pool.pop(index)

    def to_dict(self) -> dict[str, Any]:
        return {"sides": self.sides, "copies": self.copies, "pool": list(self._pool)}

    @classmethod
    def from_dict(
        cls, value: dict[str, Any], rng: RandomSource | None = None
    ) -> Roulette:
        roulette = cls(
            int(value["sides"]),
            int(value.get("copies", 1)),
            rng=rng or SystemRandomSource(),
        )
        pool = [int(face) for face in value.get("pool", [])]
        expected = roulette.sides * roulette.copies
        allowed = Counter(
            face for face in range(1, roulette.sides + 1) for _ in range(roulette.copies)
        )
        actual = Counter(pool)
        if len(pool) > expected or any(
            face < 1 or face > roulette.sides or count > allowed[face]
            for face, count in actual.items()
        ):
            raise DiceExpressionError("invalid roulette pool")
        roulette._pool = pool
        return roulette


@dataclass(frozen=True, slots=True)
class DeckEntry:
    value: str
    weight: int = 1

    def __post_init__(self) -> None:
        if not str(self.value).strip():
            raise ValueError("deck entry value must not be empty")
        if self.weight <= 0:
            raise ValueError("deck entry weight must be positive")


class Deck:
    """A weighted deck with optional replacement and serializable state."""

    def __init__(
        self,
        entries: list[DeckEntry] | tuple[DeckEntry, ...],
        *,
        rng: RandomSource | None = None,
        replace: bool = False,
    ) -> None:
        if not entries:
            raise ValueError("deck must have at least one entry")
        self.entries = tuple(entries)
        self.rng = rng or SystemRandomSource()
        self.replace = replace
        self._remaining = list(range(len(self.entries)))

    @property
    def remaining(self) -> int:
        return len(self._remaining)

    def reset(self) -> None:
        self._remaining = list(range(len(self.entries)))

    def draw(self) -> DeckEntry:
        candidates = list(range(len(self.entries))) if self.replace else self._remaining
        if not candidates:
            self.reset()
            candidates = self._remaining
        total_weight = sum(self.entries[index].weight for index in candidates)
        ticket = self.rng.randint(1, total_weight)
        chosen_index = candidates[-1]
        for index in candidates:
            ticket -= self.entries[index].weight
            if ticket <= 0:
                chosen_index = index
                break
        if not self.replace:
            self._remaining.remove(chosen_index)
        return self.entries[chosen_index]

    def to_dict(self) -> dict[str, Any]:
        return {
            "replace": self.replace,
            "entries": [
                {"value": entry.value, "weight": entry.weight} for entry in self.entries
            ],
            "remaining": list(self._remaining),
        }

    @classmethod
    def from_dict(
        cls, value: dict[str, Any], rng: RandomSource | None = None
    ) -> Deck:
        entries = tuple(
            DeckEntry(str(item["value"]), int(item.get("weight", 1)))
            for item in value["entries"]
        )
        deck = cls(entries, rng=rng, replace=bool(value.get("replace", False)))
        remaining = [int(index) for index in value.get("remaining", [])]
        if len(set(remaining)) != len(remaining) or any(
            index < 0 or index >= len(entries) for index in remaining
        ):
            raise DiceExpressionError("invalid deck remaining indexes")
        deck._remaining = remaining
        return deck


@dataclass(frozen=True, slots=True)
class L5RDie:
    color: str
    status: str = "normal"
    result: int = 0

    def __post_init__(self) -> None:
        if self.color not in {"white", "black"}:
            raise ValueError("L5R die color must be white or black")
        if self.status not in {"normal", "additional", "dropped", "rolled"}:
            raise ValueError("invalid L5R die status")
        if not 0 <= self.result <= self.sides:
            raise ValueError("L5R die result is outside its face range")

    @property
    def sides(self) -> int:
        return 12 if self.color == "white" else 6


class L5RDicePool:
    """Legend of the Five Rings white/black dice with serializable state."""

    WHITE_SYMBOLS = (
        "", "B", "B", "O", "O", "O", "S+St", "S+St", "S", "S", "S+O", "ES+St", "ES"
    )
    BLACK_SYMBOLS = ("", "B", "O+St", "O", "S+St", "S", "ES+St")

    def __init__(self, rng: RandomSource | None = None) -> None:
        self.rng = rng or SystemRandomSource()
        self.dice: list[L5RDie] = []

    def insert_white(self, count: int, *, additional: bool = False) -> None:
        self._insert("white", count, additional)

    def insert_black(self, count: int, *, additional: bool = False) -> None:
        self._insert("black", count, additional)

    def _insert(self, color: str, count: int, additional: bool) -> None:
        if count < 0 or len(self.dice) + count > 1000:
            raise DiceLimitError("L5R dice count is outside 0..1000")
        status = "additional" if additional else "normal"
        for _ in range(count):
            result = 0 if not additional else self.rng.randint(
                1, 12 if color == "white" else 6
            )
            self.dice.append(L5RDie(color, status, result))

    def roll(self) -> tuple[L5RDie, ...]:
        rolled: list[L5RDie] = []
        for index, die in enumerate(self.dice):
            if die.status == "dropped":
                continue
            result = die.result if die.status == "additional" else self.rng.randint(1, die.sides)
            status = "additional" if die.status == "additional" else "rolled"
            self.dice[index] = L5RDie(die.color, status, result)
            rolled.append(self.dice[index])
        return tuple(rolled)

    def reroll(self, position: int) -> L5RDie:
        index = self._index(position)
        die = self.dice[index]
        if die.status == "dropped":
            raise ValueError("dropped die cannot be rerolled")
        updated = L5RDie(
            die.color,
            "additional" if die.status == "additional" else "rolled",
            self.rng.randint(1, die.sides),
        )
        self.dice[index] = updated
        return updated

    def drop(self, position: int) -> None:
        index = self._index(position)
        die = self.dice[index]
        self.dice[index] = L5RDie(die.color, "dropped", die.result)

    def _index(self, position: int) -> int:
        if not 1 <= position <= len(self.dice):
            raise IndexError("L5R die position is out of range")
        return position - 1

    def result_symbols(self) -> tuple[str, ...]:
        result: list[str] = []
        for die in self.dice:
            if die.status == "dropped":
                continue
            symbols = self.WHITE_SYMBOLS if die.color == "white" else self.BLACK_SYMBOLS
            result.append(symbols[die.result] if die.result else "")
        return tuple(result)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dice": [
                {"color": die.color, "status": die.status, "result": die.result}
                for die in self.dice
            ]
        }

    @classmethod
    def from_dict(
        cls, value: dict[str, Any], rng: RandomSource | None = None
    ) -> L5RDicePool:
        pool = cls(rng)
        pool.dice = [
            L5RDie(
                str(item["color"]),
                str(item.get("status", "normal")),
                int(item.get("result", 0)),
            )
            for item in value.get("dice", [])
        ]
        if len(pool.dice) > 1000 or any(
            die.result < 0 or die.result > die.sides for die in pool.dice
        ):
            raise DiceExpressionError("invalid L5R dice state")
        return pool

    def encode(self) -> str:
        payload = " ".join(
            f"{die.color[0]}{die.result}{die.status[0] if die.status in {'additional', 'rolled'} else ''}"
            for die in self.dice
            if die.status != "dropped"
        )
        return base64.b64encode(payload.encode("ascii")).decode("ascii")

    @classmethod
    def decode(cls, encoded: str, rng: RandomSource | None = None) -> L5RDicePool:
        try:
            payload = base64.b64decode(encoded.encode("ascii"), validate=True).decode("ascii")
        except (binascii.Error, UnicodeDecodeError) as error:
            raise DiceExpressionError("invalid L5R encoded state") from error
        pool = cls(rng)
        for item in payload.split():
            if len(item) < 2 or item[0] not in {"w", "b"}:
                raise DiceExpressionError("invalid L5R die token")
            color = "white" if item[0] == "w" else "black"
            suffix = item[-1] if item[-1] in {"a", "r"} else ""
            number = item[1:-1] if suffix else item[1:]
            if not number.isdigit():
                raise DiceExpressionError("invalid L5R die result")
            result = int(number)
            if result > (12 if color == "white" else 6):
                raise DiceExpressionError("L5R die result is outside its face range")
            pool.dice.append(
                L5RDie(
                    color,
                    {"a": "additional", "r": "rolled", "": "normal"}[suffix],
                    result,
                )
            )
        return pool
