from __future__ import annotations

from dataclasses import dataclass

from .errors import DiceExpressionError, DiceLimitError, DivisionByZeroError
from .models import CheckResult, DiceTermResult, PoolResult, RollResult
from .randomness import RandomSource, SystemRandomSource


@dataclass(frozen=True, slots=True)
class RollLimits:
    max_expression_length: int = 512
    max_dice_count: int = 1000
    max_sides: int = 1_000_000
    max_special_dice: int = 9
    max_total_rolls: int = 10_000
    max_abs_total: int = 10**15


class _Node:
    precedence = 100

    def render(self, parent_precedence: int = 0) -> str:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class _Number(_Node):
    value: int

    def render(self, parent_precedence: int = 0) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class _Dice(_Node):
    count: int
    sides: int | None = None
    keep: int | None = None
    fate: bool = False

    def render(self, parent_precedence: int = 0) -> str:
        if self.fate:
            return f"{self.count}dF"
        result = f"{self.count}d{self.sides}"
        if self.keep is not None:
            result += f"K{self.keep}"
        return result


@dataclass(frozen=True, slots=True)
class _Percentile(_Node):
    count: int
    bonus: bool

    def render(self, parent_precedence: int = 0) -> str:
        return f"{'B' if self.bonus else 'P'}{self.count}"


@dataclass(frozen=True, slots=True)
class _Unary(_Node):
    operator: str
    operand: _Node
    precedence = 30

    def render(self, parent_precedence: int = 0) -> str:
        result = f"{self.operator}{self.operand.render(self.precedence)}"
        return f"({result})" if self.precedence < parent_precedence else result


@dataclass(frozen=True, slots=True)
class _Binary(_Node):
    operator: str
    left: _Node
    right: _Node
    precedence = 10

    def __post_init__(self) -> None:
        object.__setattr__(self, "precedence", 20 if self.operator in {"*", "/"} else 10)

    def render(self, parent_precedence: int = 0) -> str:
        left = self.left.render(self.precedence)
        right_precedence = self.precedence + (1 if self.operator in {"-", "/"} else 0)
        right = self.right.render(right_precedence)
        result = f"{left}{self.operator}{right}"
        return f"({result})" if self.precedence < parent_precedence else result


class _Parser:
    def __init__(self, expression: str, default_sides: int, limits: RollLimits) -> None:
        compact = "".join(expression.split())
        self.original = expression
        self.text = compact or f"d{default_sides}"
        self.default_sides = default_sides
        self.limits = limits
        self.position = 0
        if len(self.text) > limits.max_expression_length:
            raise DiceLimitError("dice expression is too long")

    def parse(self) -> _Node:
        node = self._expression()
        if self.position != len(self.text):
            raise self._error(f"unexpected token {self.text[self.position]!r}")
        return node

    def _expression(self) -> _Node:
        node = self._term()
        while (operator := self._accept_any("+-")) is not None:
            node = _Binary(operator, node, self._term())
        return node

    def _term(self) -> _Node:
        node = self._unary()
        while (operator := self._accept_any("*/xX")) is not None:
            if operator in {"x", "X"}:
                operator = "*"
            node = _Binary(operator, node, self._unary())
        return node

    def _unary(self) -> _Node:
        if (operator := self._accept_any("+-")) is not None:
            return _Unary(operator, self._unary())
        return self._primary()

    def _primary(self) -> _Node:
        if self._accept("("):
            node = self._expression()
            if not self._accept(")"):
                raise self._error("missing closing parenthesis")
            return node

        current = self._peek().upper()
        if current in {"B", "P"}:
            self.position += 1
            count_text = self._digits()
            count = int(count_text) if count_text else 1
            if not 1 <= count <= self.limits.max_special_dice:
                raise DiceLimitError(
                    f"bonus/penalty count must be in 1..{self.limits.max_special_dice}"
                )
            return _Percentile(count=count, bonus=current == "B")

        if current == "F":
            self.position += 1
            return self._validated_dice(count=4, fate=True)

        if current == "D":
            self.position += 1
            if self._peek().upper() == "F":
                self.position += 1
                return self._validated_dice(count=4, fate=True)
            return self._normal_dice(count=1)

        number_text = self._digits()
        if not number_text:
            if not self._peek():
                raise self._error("expression ended unexpectedly")
            raise self._error(f"unexpected token {self._peek()!r}")
        number = int(number_text)

        if self._peek().upper() == "D":
            self.position += 1
            if self._peek().upper() == "F":
                self.position += 1
                return self._validated_dice(count=number, fate=True)
            return self._normal_dice(count=number)
        if self._peek().upper() == "F":
            self.position += 1
            return self._validated_dice(count=number, fate=True)
        return _Number(number)

    def _normal_dice(self, count: int) -> _Dice:
        sides_text = self._digits()
        sides = int(sides_text) if sides_text else self.default_sides
        keep: int | None = None
        if self._peek().upper() == "K":
            self.position += 1
            keep_text = self._digits()
            keep = int(keep_text) if keep_text else 1
        return self._validated_dice(count=count, sides=sides, keep=keep)

    def _validated_dice(
        self,
        *,
        count: int,
        sides: int | None = None,
        keep: int | None = None,
        fate: bool = False,
    ) -> _Dice:
        if count <= 0:
            raise DiceExpressionError("dice count must be positive")
        if count > self.limits.max_dice_count:
            raise DiceLimitError(
                f"dice count {count} exceeds {self.limits.max_dice_count}"
            )
        if not fate:
            if sides is None or sides <= 0:
                raise DiceExpressionError("dice sides must be positive")
            if sides > self.limits.max_sides:
                raise DiceLimitError(
                    f"dice sides {sides} exceeds {self.limits.max_sides}"
                )
        if keep is not None and not 1 <= keep <= count:
            raise DiceExpressionError("kept dice count must be in 1..dice count")
        return _Dice(count=count, sides=sides, keep=keep, fate=fate)

    def _digits(self) -> str:
        start = self.position
        while self._peek().isdigit():
            self.position += 1
        return self.text[start : self.position]

    def _peek(self) -> str:
        if self.position >= len(self.text):
            return ""
        return self.text[self.position]

    def _accept(self, token: str) -> bool:
        if self._peek() == token:
            self.position += 1
            return True
        return False

    def _accept_any(self, tokens: str) -> str | None:
        current = self._peek()
        if current and current in tokens:
            self.position += 1
            return current
        return None

    def _error(self, message: str) -> DiceExpressionError:
        return DiceExpressionError(f"{message} at position {self.position}")


@dataclass(slots=True)
class _Evaluation:
    rng: RandomSource
    limits: RollLimits
    terms: list[DiceTermResult]
    roll_count: int = 0

    def consume_rolls(self, count: int) -> None:
        self.roll_count += count
        if self.roll_count > self.limits.max_total_rolls:
            raise DiceLimitError(
                f"expression rolls more than {self.limits.max_total_rolls} dice"
            )


class DiceRoller:
    """Pure dice engine with no messaging-platform dependencies."""

    def __init__(
        self,
        rng: RandomSource | None = None,
        *,
        default_sides: int = 100,
        limits: RollLimits | None = None,
    ) -> None:
        self.rng = rng or SystemRandomSource()
        self.default_sides = default_sides
        self.limits = limits or RollLimits()
        if not 1 <= default_sides <= self.limits.max_sides:
            raise ValueError("default_sides is outside configured limits")

    def normalize(self, expression: str = "") -> str:
        node = _Parser(expression, self.default_sides, self.limits).parse()
        return node.render()

    def roll(self, expression: str = "") -> RollResult:
        node = _Parser(expression, self.default_sides, self.limits).parse()
        evaluation = _Evaluation(self.rng, self.limits, [])
        total = self._evaluate(node, evaluation)
        self._validate_total(total)
        return RollResult(
            expression=expression,
            normalized_expression=node.render(),
            total=total,
            terms=tuple(evaluation.terms),
        )

    def randint(self, lower: int, upper: int) -> int:
        if lower > upper:
            raise ValueError("lower must not exceed upper")
        return self.rng.randint(lower, upper)

    def bonus(self, count: int = 1) -> RollResult:
        return self.roll(f"B{count}")

    def penalty(self, count: int = 1) -> RollResult:
        return self.roll(f"P{count}")

    def pool(
        self,
        count: int,
        *,
        sides: int = 10,
        target: int = 8,
        explode_at: int | None = 10,
        max_explosions: int = 1000,
    ) -> PoolResult:
        if not 1 <= count <= self.limits.max_dice_count:
            raise DiceLimitError(
                f"pool count must be in 1..{self.limits.max_dice_count}"
            )
        if not 1 <= sides <= self.limits.max_sides:
            raise DiceLimitError(f"pool sides must be in 1..{self.limits.max_sides}")
        if not 1 <= target <= sides:
            raise DiceExpressionError("pool target must be in 1..sides")
        if explode_at is not None and not 1 <= explode_at <= sides + 1:
            raise DiceExpressionError("explode_at must be in 1..sides+1 or None")
        if max_explosions < 0:
            raise ValueError("max_explosions must be non-negative")

        pending = count
        explosions = 0
        rolls: list[int] = []
        while pending:
            pending -= 1
            value = self.rng.randint(1, sides)
            rolls.append(value)
            if explode_at is not None and value >= explode_at:
                explosions += 1
                if explosions > max_explosions:
                    raise DiceLimitError("dice pool exceeded max_explosions")
                pending += 1
        successes = sum(value >= target for value in rolls)
        return PoolResult(
            count=count,
            sides=sides,
            target=target,
            explode_at=explode_at,
            rolls=tuple(rolls),
            successes=successes,
        )

    def coc_check(
        self,
        target: int,
        *,
        bonus_dice: int = 0,
        penalty_dice: int = 0,
        rule: int = 0,
    ) -> CheckResult:
        if target < 0:
            raise ValueError("target must be non-negative")
        if bonus_dice and penalty_dice:
            raise ValueError("bonus_dice and penalty_dice are mutually exclusive")
        if bonus_dice:
            roll = self.bonus(bonus_dice)
        elif penalty_dice:
            roll = self.penalty(penalty_dice)
        else:
            roll = self.roll("1d100")
        level = coc_success_level(roll.total, target, rule)
        return CheckResult(target=target, roll=roll, success_level=level, rule=rule)

    def _evaluate(self, node: _Node, evaluation: _Evaluation) -> int:
        if isinstance(node, _Number):
            return node.value
        if isinstance(node, _Unary):
            value = self._evaluate(node.operand, evaluation)
            return value if node.operator == "+" else -value
        if isinstance(node, _Binary):
            left = self._evaluate(node.left, evaluation)
            right = self._evaluate(node.right, evaluation)
            if node.operator == "+":
                value = left + right
            elif node.operator == "-":
                value = left - right
            elif node.operator == "*":
                value = left * right
            else:
                if right == 0:
                    raise DivisionByZeroError("cannot divide by zero")
                value = (abs(left) // abs(right)) * (-1 if (left < 0) != (right < 0) else 1)
            self._validate_total(value)
            return value
        if isinstance(node, _Percentile):
            return self._roll_percentile(node, evaluation)
        if isinstance(node, _Dice):
            return self._roll_dice(node, evaluation)
        raise TypeError(f"unsupported node: {type(node)!r}")

    def _roll_dice(self, node: _Dice, evaluation: _Evaluation) -> int:
        evaluation.consume_rolls(node.count)
        if node.fate:
            rolls = tuple(self.rng.randint(-1, 1) for _ in range(node.count))
            subtotal = sum(rolls)
            evaluation.terms.append(
                DiceTermResult(
                    notation=node.render(),
                    kind="fate",
                    count=node.count,
                    sides=3,
                    rolls=rolls,
                    kept=rolls,
                    subtotal=subtotal,
                )
            )
            return subtotal

        assert node.sides is not None
        rolls = tuple(self.rng.randint(1, node.sides) for _ in range(node.count))
        if node.keep is None:
            kept = rolls
            dropped: tuple[int, ...] = ()
        else:
            ranked = sorted(enumerate(rolls), key=lambda item: (-item[1], item[0]))
            kept_indexes = {index for index, _ in ranked[: node.keep]}
            kept = tuple(value for index, value in enumerate(rolls) if index in kept_indexes)
            dropped = tuple(
                value for index, value in enumerate(rolls) if index not in kept_indexes
            )
        subtotal = sum(kept)
        evaluation.terms.append(
            DiceTermResult(
                notation=node.render(),
                kind="dice",
                count=node.count,
                sides=node.sides,
                rolls=rolls,
                kept=kept,
                dropped=dropped,
                subtotal=subtotal,
            )
        )
        return subtotal

    def _roll_percentile(self, node: _Percentile, evaluation: _Evaluation) -> int:
        evaluation.consume_rolls(node.count + 1)
        base = self.rng.randint(1, 100)
        ones = base % 10
        base_tens = 10 if base == 100 else base // 10
        extra_tens: list[int] = []
        for _ in range(node.count):
            raw = self.rng.randint(1, 10)
            extra_tens.append(raw if ones == 0 else raw - 1)
        choices = [base_tens, *extra_tens]
        chosen_tens = min(choices) if node.bonus else max(choices)
        subtotal = chosen_tens * 10 + ones
        evaluation.terms.append(
            DiceTermResult(
                notation=node.render(),
                kind="bonus" if node.bonus else "penalty",
                subtotal=subtotal,
                rolls=(base,),
                kept=(subtotal,),
                base_roll=base,
                extra_tens=tuple(extra_tens),
                count=node.count,
                sides=100,
            )
        )
        return subtotal

    def _validate_total(self, value: int) -> None:
        if abs(value) > self.limits.max_abs_total:
            raise DiceLimitError(
                f"absolute result exceeds {self.limits.max_abs_total}"
            )


def coc_success_level(result: int, target: int, rule: int = 0) -> str:
    if not 1 <= result <= 100:
        raise ValueError("COC result must be in 1..100")
    if target < 0:
        raise ValueError("COC target must be non-negative")
    if not 0 <= rule <= 7:
        raise ValueError("COC rule must be in 0..7")

    if rule == 0:
        if result == 100:
            return "fumble"
        if result == 1:
            return "critical"
        if result <= target // 5:
            return "extreme_success"
        if result <= target // 2:
            return "hard_success"
        if result <= target:
            return "regular_success"
        return "failure" if target >= 50 or result < 96 else "fumble"
    if rule == 1:
        if result == 100:
            return "fumble"
        if result == 1 or (result <= 5 and target >= 50):
            return "critical"
        if result <= target // 5:
            return "extreme_success"
        if result <= target // 2:
            return "hard_success"
        if result <= target:
            return "regular_success"
        return "failure" if target >= 50 or result < 96 else "fumble"
    if rule == 2:
        if result == 100:
            return "fumble"
        if result <= 5 and result <= target:
            return "critical"
        if result <= target // 5:
            return "extreme_success"
        if result <= target // 2:
            return "hard_success"
        if result <= target:
            return "regular_success"
        return "failure" if result < 96 else "fumble"
    if rule == 3:
        if result >= 96:
            return "fumble"
        if result <= 5:
            return "critical"
        if result <= target // 5:
            return "extreme_success"
        if result <= target // 2:
            return "hard_success"
        if result <= target:
            return "regular_success"
        return "failure"
    if rule == 4:
        if result == 100:
            return "fumble"
        if result <= 5 and result <= target // 10:
            return "critical"
        if result <= target // 5:
            return "extreme_success"
        if result <= target // 2:
            return "hard_success"
        if result <= target:
            return "regular_success"
        return "failure" if target >= 50 or result < 96 + target // 10 else "fumble"
    if rule == 5:
        if result >= 99:
            return "fumble"
        if result <= 2 and result < target // 10:
            return "critical"
        if result <= target // 5:
            return "extreme_success"
        if result <= target // 2:
            return "hard_success"
        if result <= target:
            return "regular_success"
        return "failure" if target >= 50 or result < 96 else "fumble"
    if rule == 6:
        if result > target:
            return "fumble" if result == 100 or result % 11 == 0 else "failure"
        return "critical" if result == 1 or result % 11 == 0 else "regular_success"

    if result >= 100:
        return "fumble"
    if result >= 96:
        return "fumble" if (90 - target) // 20 + result >= 100 else "failure"
    if result == 1 or result <= (target + 2) // 5:
        return "extreme_success"
    return "regular_success" if result <= target else "failure"
