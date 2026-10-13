from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .errors import IdentityError, NotFoundError
from .models import ActorRef, MessageSource
from .randomness import RandomSource, SystemRandomSource
from .special import Deck, DeckEntry, Roulette
from .storage import JsonStore


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


@dataclass(slots=True)
class DiceSession:
    """A platform-neutral TRPG room and its persistent dice state."""

    session_id: str
    rng: RandomSource = field(default_factory=SystemRandomSource, repr=False)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    sources: set[MessageSource] = field(default_factory=set)
    game_masters: set[ActorRef] = field(default_factory=set)
    players: set[ActorRef] = field(default_factory=set)
    observers: set[ActorRef] = field(default_factory=set)
    data: dict[str, Any] = field(default_factory=dict)
    roulettes: dict[int, Roulette] = field(default_factory=dict)
    decks: dict[str, Deck] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.session_id = str(self.session_id).strip()
        if not self.session_id:
            raise IdentityError("session_id must not be empty")

    def add_source(self, source: MessageSource) -> None:
        self.sources.add(source)
        self.touch()

    def remove_source(self, source: MessageSource) -> bool:
        existed = source in self.sources
        self.sources.discard(source)
        if existed:
            self.touch()
        return existed

    def add_gm(self, actor: ActorRef) -> bool:
        existed = actor in self.game_masters
        self.game_masters.add(actor)
        self.players.discard(actor)
        self.observers.discard(actor)
        self.touch()
        return not existed

    def remove_gm(self, actor: ActorRef) -> bool:
        existed = actor in self.game_masters
        self.game_masters.discard(actor)
        if existed:
            self.touch()
        return existed

    def add_player(self, actor: ActorRef) -> bool:
        if actor in self.game_masters:
            return False
        existed = actor in self.players
        self.players.add(actor)
        self.observers.discard(actor)
        self.touch()
        return not existed

    def remove_player(self, actor: ActorRef) -> bool:
        existed = actor in self.players
        self.players.discard(actor)
        if existed:
            self.touch()
        return existed

    def remove_observer(self, actor: ActorRef) -> bool:
        existed = actor in self.observers
        self.observers.discard(actor)
        if existed:
            self.touch()
        return existed

    def add_observer(self, actor: ActorRef) -> bool:
        existed = actor in self.observers
        self.observers.add(actor)
        self.touch()
        return not existed

    def roll(self, sides: int) -> int:
        if sides <= 0:
            raise ValueError("sides must be positive")
        roulette = self.roulettes.get(sides)
        result = roulette.roll() if roulette is not None else self.rng.randint(1, sides)
        self.touch()
        return result

    def configure_roulette(self, sides: int, copies: int = 1) -> Roulette:
        roulette = Roulette(sides, copies, rng=self.rng)
        self.roulettes[sides] = roulette
        self.touch()
        return roulette

    def configure_deck(
        self,
        name: str,
        entries: list[DeckEntry] | tuple[DeckEntry, ...],
        *,
        replace: bool = False,
    ) -> Deck:
        key = str(name).strip()
        if not key:
            raise IdentityError("deck name must not be empty")
        deck = Deck(entries, rng=self.rng, replace=replace)
        self.decks[key] = deck
        self.touch()
        return deck

    def draw(self, name: str) -> DeckEntry:
        try:
            deck = self.decks[str(name)]
        except KeyError as error:
            raise NotFoundError(f"deck {name!r} does not exist") from error
        entry = deck.draw()
        self.touch()
        return entry

    def touch(self) -> None:
        self.updated_at = _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "sources": [source.to_dict() for source in sorted(self.sources, key=lambda item: item.key)],
            "game_masters": [actor.to_dict() for actor in sorted(self.game_masters, key=lambda item: item.key)],
            "players": [actor.to_dict() for actor in sorted(self.players, key=lambda item: item.key)],
            "observers": [actor.to_dict() for actor in sorted(self.observers, key=lambda item: item.key)],
            "data": self.data,
            "roulettes": {str(sides): roulette.to_dict() for sides, roulette in self.roulettes.items()},
            "decks": {name: deck.to_dict() for name, deck in self.decks.items()},
        }

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
        *,
        rng: RandomSource | None = None,
    ) -> DiceSession:
        source = rng or SystemRandomSource()
        session = cls(
            session_id=str(value["session_id"]),
            rng=source,
            created_at=str(value.get("created_at", _now())),
            updated_at=str(value.get("updated_at", _now())),
            sources={MessageSource.from_dict(dict(item)) for item in value.get("sources", [])},
            game_masters={ActorRef.from_dict(dict(item)) for item in value.get("game_masters", [])},
            players={ActorRef.from_dict(dict(item)) for item in value.get("players", [])},
            observers={ActorRef.from_dict(dict(item)) for item in value.get("observers", [])},
            data=dict(value.get("data", {})),
        )
        session.roulettes = {
            int(sides): Roulette.from_dict(dict(item), rng=source)
            for sides, item in dict(value.get("roulettes", {})).items()
        }
        session.decks = {
            str(name): Deck.from_dict(dict(item), rng=source)
            for name, item in dict(value.get("decks", {})).items()
        }
        return session


class SessionRepository:
    def __init__(self, root: str) -> None:
        self.store = JsonStore(root)

    def load(self, session_id: str, rng: RandomSource | None = None) -> DiceSession:
        value = self.store.read(self.path_for(session_id))
        if value is None:
            return DiceSession(session_id, rng=rng or SystemRandomSource())
        return DiceSession.from_dict(value, rng=rng)

    def save(self, session: DiceSession) -> None:
        session.touch()
        self.store.write(self.path_for(session.session_id), session.to_dict())

    @staticmethod
    def path_for(session_id: str) -> str:
        normalized = str(session_id).strip()
        if not normalized:
            raise IdentityError("session_id must not be empty")
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"sessions/{digest}.json"
