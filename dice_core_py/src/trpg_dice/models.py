from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass(frozen=True, slots=True)
class PoolResult:
    count: int
    sides: int
    target: int
    explode_at: int | None
    rolls: tuple[int, ...]
    successes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "sides": self.sides,
            "target": self.target,
            "explode_at": self.explode_at,
            "rolls": list(self.rolls),
            "successes": self.successes,
        }


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
