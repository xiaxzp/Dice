from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any
from urllib.parse import quote


def _required(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class ActorRef:
    platform: str
    user_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "platform", _required(self.platform, "platform"))
        object.__setattr__(self, "user_id", _required(self.user_id, "user_id"))

    @property
    def key(self) -> str:
        return f"{quote(self.platform, safe='')}:{quote(self.user_id, safe='')}"

    def to_dict(self) -> dict[str, str]:
        return {"platform": self.platform, "user_id": self.user_id}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ActorRef:
        return cls(platform=str(value["platform"]), user_id=str(value["user_id"]))


@dataclass(frozen=True, slots=True)
class MessageSource:
    platform: str
    kind: str
    source_id: str
    channel_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "platform", _required(self.platform, "platform"))
        object.__setattr__(self, "kind", _required(self.kind, "kind"))
        object.__setattr__(self, "source_id", _required(self.source_id, "source_id"))
        if self.channel_id is not None:
            object.__setattr__(
                self, "channel_id", _required(self.channel_id, "channel_id")
            )

    @property
    def key(self) -> str:
        parts = [self.platform, self.kind, self.source_id]
        if self.channel_id is not None:
            parts.append(self.channel_id)
        return ":".join(quote(part, safe="") for part in parts)

    def to_dict(self) -> dict[str, str]:
        result = {
            "platform": self.platform,
            "kind": self.kind,
            "source_id": self.source_id,
        }
        if self.channel_id is not None:
            result["channel_id"] = self.channel_id
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> MessageSource:
        channel_id = value.get("channel_id")
        return cls(
            platform=str(value["platform"]),
            kind=str(value["kind"]),
            source_id=str(value["source_id"]),
            channel_id=None if channel_id is None else str(channel_id),
        )


@dataclass(frozen=True, slots=True)
class MessageContext:
    actor: ActorRef
    source: MessageSource
    account_nickname: str | None = None
    source_nickname: str | None = None

    def __post_init__(self) -> None:
        if self.actor.platform != self.source.platform:
            raise ValueError("actor and source must use the same platform")


@dataclass(frozen=True, slots=True)
class DiceTermResult:
    notation: str
    kind: str
    subtotal: int
    rolls: tuple[int, ...] = ()
    kept: tuple[int, ...] = ()
    dropped: tuple[int, ...] = ()
    count: int | None = None
    sides: int | None = None
    base_roll: int | None = None
    extra_tens: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "notation": self.notation,
            "kind": self.kind,
            "subtotal": self.subtotal,
            "rolls": list(self.rolls),
            "kept": list(self.kept),
            "dropped": list(self.dropped),
            "count": self.count,
            "sides": self.sides,
            "base_roll": self.base_roll,
            "extra_tens": list(self.extra_tens),
        }


@dataclass(frozen=True, slots=True)
class RollResult:
    expression: str
    normalized_expression: str
    total: int
    terms: tuple[DiceTermResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "normalized_expression": self.normalized_expression,
            "total": self.total,
            "terms": [term.to_dict() for term in self.terms],
        }

    def render(self) -> str:
        details: list[str] = []
        for term in self.terms:
            if term.kind == "bonus":
                details.append(
                    f"{term.notation}={term.subtotal}"
                    f"(基础={term.base_roll}, 额外十位={list(term.extra_tens)})"
                )
            elif term.kind == "penalty":
                details.append(
                    f"{term.notation}={term.subtotal}"
                    f"(基础={term.base_roll}, 额外十位={list(term.extra_tens)})"
                )
            elif term.kind == "fate":
                details.append(f"{term.notation}={list(term.rolls)}")
            elif term.dropped:
                details.append(
                    f"{term.notation}={list(term.rolls)}"
                    f"(保留={list(term.kept)})"
                )
            else:
                details.append(f"{term.notation}={list(term.rolls)}")
        suffix = f" [{'; '.join(details)}]" if details else ""
        return f"{self.normalized_expression} = {self.total}{suffix}"

    def render_c(self) -> str:
        expression = self._c_expression()
        if not expression:
            expression = self.normalized_expression.upper()
        if expression.startswith("1D") and not self.expression.strip()[:1].isdigit():
            expression = expression[1:]
        separate = self._c_separate()
        combined = self._c_combined()
        if expression == separate and len(self.terms) == 1:
            return expression
        rendered = expression
        if expression != separate:
            rendered += f"={separate}"
        if separate != combined:
            rendered += f"={combined}"
        if combined != str(self.total):
            rendered += f"={self.total}"
        return rendered

    def render_c_value(self, detailed: bool = False) -> str:
        if len(self.terms) != 1:
            return str(self.total)
        if not detailed:
            term = self.terms[0]
            if term.kind in {"bonus", "penalty"}:
                label = "奖励骰" if term.kind == "bonus" else "惩罚骰"
                extras = " ".join(str(value) for value in term.extra_tens)
                return f"{term.base_roll}[{label}:{extras}]={term.subtotal}"
            return str(self.total)
        separate = self._c_separate()
        combined = self._c_combined()
        if separate != self._c_expression() and separate != combined:
            return f"{separate}={self.total}"
        if combined != str(self.total):
            return f"{combined}={self.total}"
        return str(self.total)

    def _c_expression(self) -> str:
        expression = (
            self.normalized_expression.upper()
            .replace("*", "X")
            .replace("/", "/")
        )
        raw = self.expression.strip()
        if raw and raw[:1].casefold() == "d" and expression.startswith("1D"):
            expression = expression[1:]
        elif not raw and expression.startswith("1D"):
            expression = expression[1:]
        return expression

    @staticmethod
    def _c_term_separate(term: DiceTermResult) -> str:
        if term.kind in {"bonus", "penalty"}:
            label = "奖励骰" if term.kind == "bonus" else "惩罚骰"
            extras = " ".join(str(value) for value in term.extra_tens)
            return f"{term.base_roll}[{label}:{extras}]"
        if term.kind == "fate":
            return "[" + " ".join("+" if value == 1 else "0" if value == 0 else "-" for value in term.rolls) + "]"
        values = term.kept or term.rolls
        return "+".join(str(value) for value in values) or str(term.subtotal)

    def _c_separate(self) -> str:
        expression = self._c_expression()
        for term in self.terms:
            replacement = self._c_term_separate(term)
            if len(self.terms) > 1 and len(term.rolls) > 1:
                replacement = f"({replacement})"
            notation = term.notation.upper()
            if notation.startswith("1D") and notation not in expression:
                notation = notation[1:]
            expression = re.sub(
                re.escape(notation),
                lambda _: replacement,
                expression,
                count=1,
            )
        return expression

    def _c_combined(self) -> str:
        expression = self._c_expression()
        for term in self.terms:
            notation = term.notation.upper()
            if notation.startswith("1D") and notation not in expression:
                notation = notation[1:]
            expression = re.sub(
                re.escape(notation),
                lambda _: str(term.subtotal),
                expression,
                count=1,
            )
        return expression


@dataclass(frozen=True, slots=True)
class PoolResult:
    count: int
    sides: int
    target: int
    explode_at: int | None
    rolls: tuple[int, ...]
    successes: int
    groups: tuple[tuple[int, ...], ...] = ()
    success_groups: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "sides": self.sides,
            "target": self.target,
            "explode_at": self.explode_at,
            "rolls": list(self.rolls),
            "successes": self.successes,
            "groups": [list(group) for group in self.groups],
            "success_groups": list(self.success_groups),
        }

    @staticmethod
    def _circled(value: int, target: int) -> str:
        if value < target:
            return str(value)
        return chr(0x245F + value)

    def render_c(self, notation: str, *, detailed: bool) -> str:
        groups = self.groups or (self.rolls,)
        separate = "+".join(
            "{" + ",".join(self._circled(value, self.target) for value in group) + "}"
            for group in groups
        )
        combined_values = self.success_groups or (self.successes,)
        combined = "+".join(str(value) for value in combined_values)
        if not detailed:
            rendered = notation
            if notation != combined:
                rendered += f"={combined}"
            if combined != str(self.successes):
                rendered += f"={self.successes}"
            return rendered
        rendered = notation
        if notation != separate:
            rendered += f"={separate}"
        if separate != combined:
            rendered += f"={combined}"
        if combined != str(self.successes):
            rendered += f"={self.successes}"
        return rendered


@dataclass(frozen=True, slots=True)
class CheckResult:
    target: int
    roll: RollResult
    success_level: str
    rule: int

    @property
    def success(self) -> bool:
        return self.success_level not in {"failure", "fumble"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "roll": self.roll.to_dict(),
            "success_level": self.success_level,
            "success": self.success,
            "rule": self.rule,
        }


@dataclass(frozen=True, slots=True)
class RollRequest:
    context: MessageContext
    expression: str = ""
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RollResponse:
    request: RollRequest
    display_name: str
    card_id: str | None
    card_name: str | None
    result: RollResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.request.context.actor.to_dict(),
            "source": self.request.context.source.to_dict(),
            "reason": self.request.reason,
            "display_name": self.display_name,
            "card_id": self.card_id,
            "card_name": self.card_name,
            "result": self.result.to_dict(),
        }
