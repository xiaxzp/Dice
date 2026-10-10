from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

from .errors import ConflictError, IdentityError, NotFoundError
from .models import ActorRef, MessageContext, MessageSource
from .storage import JsonStore


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _clean_name(value: str, field_name: str = "name") -> str:
    normalized = str(value).strip()
    if not normalized:
        raise IdentityError(f"{field_name} must not be empty")
    if "\n" in normalized or "\r" in normalized:
        raise IdentityError(f"{field_name} must not contain line breaks")
    return normalized


@dataclass(frozen=True, slots=True)
class CharacterCard:
    card_id: str
    name: str
    system: str = "generic"
    attributes: dict[str, Any] = field(default_factory=dict)
    locks: frozenset[str] = frozenset()
    updated_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "card_id", _clean_name(self.card_id, "card_id"))
        object.__setattr__(self, "name", _clean_name(self.name))
        object.__setattr__(self, "system", _clean_name(self.system, "system"))
        object.__setattr__(self, "attributes", dict(self.attributes))
        object.__setattr__(self, "locks", frozenset(str(lock) for lock in self.locks))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.card_id,
            "name": self.name,
            "system": self.system,
            "attributes": self.attributes,
            "locks": sorted(self.locks),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CharacterCard:
        return cls(
            card_id=str(value["id"]),
            name=str(value["name"]),
            system=str(value.get("system", "generic")),
            attributes=dict(value.get("attributes", {})),
            locks=frozenset(str(lock) for lock in value.get("locks", [])),
            updated_at=str(value.get("updated_at", _now())),
        )


@dataclass(slots=True)
class Profile:
    actor: ActorRef
    nicknames: dict[str, str] = field(default_factory=dict)
    cards: dict[str, CharacterCard] = field(default_factory=dict)
    bindings: dict[str, str] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    next_card_id: int = 1

    schema_version = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "actor": self.actor.to_dict(),
            "nicknames": dict(self.nicknames),
            "cards": {card_id: card.to_dict() for card_id, card in self.cards.items()},
            "bindings": dict(self.bindings),
            "settings": dict(self.settings),
            "next_card_id": self.next_card_id,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Profile:
        actor = ActorRef.from_dict(dict(value["actor"]))
        cards = {
            str(card_id): CharacterCard.from_dict(dict(card))
            for card_id, card in dict(value.get("cards", {})).items()
        }
        next_card_id = int(value.get("next_card_id", 1))
        if cards:
            numeric_ids = [int(card_id) for card_id in cards if card_id.isdigit()]
            if numeric_ids:
                next_card_id = max(next_card_id, max(numeric_ids) + 1)
        return cls(
            actor=actor,
            nicknames={str(key): str(name) for key, name in dict(value.get("nicknames", {})).items()},
            cards=cards,
            bindings={str(key): str(card_id) for key, card_id in dict(value.get("bindings", {})).items()},
            settings=dict(value.get("settings", {})),
            next_card_id=max(1, next_card_id),
        )


class ProfileRepository:
    def __init__(self, root: str) -> None:
        self.store = JsonStore(root)

    def load(self, actor: ActorRef) -> Profile:
        value = self.store.read(self.path_for(actor))
        return Profile(actor=actor) if value is None else Profile.from_dict(value)

    def save(self, profile: Profile) -> None:
        self.store.write(self.path_for(profile.actor), profile.to_dict())

    @staticmethod
    def path_for(actor: ActorRef) -> str:
        import hashlib

        digest = hashlib.sha256(actor.key.encode("utf-8")).hexdigest()
        return f"profiles/{digest}.json"


class CharacterService:
    """Character cards and source bindings for opaque platform identities."""

    def __init__(self, repository: ProfileRepository) -> None:
        self.repository = repository

    def list(self, actor: ActorRef) -> list[CharacterCard]:
        profile = self.repository.load(actor)
        return sorted(
            profile.cards.values(),
            key=lambda card: (
                0 if card.card_id.isdigit() else 1,
                int(card.card_id) if card.card_id.isdigit() else card.card_id,
            ),
        )

    def get(self, actor: ActorRef, card_id: str) -> CharacterCard:
        profile = self.repository.load(actor)
        try:
            return profile.cards[str(card_id)]
        except KeyError as error:
            raise NotFoundError(f"character card {card_id!r} does not exist") from error

    def create(
        self,
        actor: ActorRef,
        name: str,
        *,
        system: str = "generic",
        attributes: dict[str, Any] | None = None,
        locks: set[str] | frozenset[str] | None = None,
    ) -> CharacterCard:
        profile = self.repository.load(actor)
        normalized_name = _clean_name(name)
        if any(card.name.casefold() == normalized_name.casefold() for card in profile.cards.values()):
            raise ConflictError(f"character card name {normalized_name!r} already exists")
        card_id = str(profile.next_card_id)
        card = CharacterCard(
            card_id=card_id,
            name=normalized_name,
            system=system,
            attributes=attributes or {},
            locks=locks or frozenset(),
        )
        profile.cards[card_id] = card
        profile.next_card_id += 1
        self.repository.save(profile)
        return card

    def update(
        self,
        actor: ActorRef,
        card_id: str,
        *,
        attributes: dict[str, Any] | None = None,
        system: str | None = None,
    ) -> CharacterCard:
        profile = self.repository.load(actor)
        card = self.get(actor, card_id)
        if "q" in card.locks:
            raise IdentityError("character card is locked for updates")
        updated = replace(
            card,
            attributes=dict(card.attributes if attributes is None else attributes),
            system=card.system if system is None else system,
            updated_at=_now(),
        )
        profile.cards[updated.card_id] = updated
        self.repository.save(profile)
        return updated

    def rename(self, actor: ActorRef, card_id: str, name: str) -> CharacterCard:
        profile = self.repository.load(actor)
        card = self.get(actor, card_id)
        normalized_name = _clean_name(name)
        if "n" in card.locks:
            raise IdentityError("character card is locked for renaming")
        if any(
            other.card_id != card.card_id
            and other.name.casefold() == normalized_name.casefold()
            for other in profile.cards.values()
        ):
            raise ConflictError(f"character card name {normalized_name!r} already exists")
        updated = replace(card, name=normalized_name, updated_at=_now())
        profile.cards[updated.card_id] = updated
        self.repository.save(profile)
        return updated

    def delete(self, actor: ActorRef, card_id: str) -> None:
        profile = self.repository.load(actor)
        card = self.get(actor, card_id)
        if "q" in card.locks:
            raise IdentityError("character card is locked for deletion")
        del profile.cards[card.card_id]
        profile.bindings = {
            scope: bound_id
            for scope, bound_id in profile.bindings.items()
            if bound_id != card.card_id
        }
        self.repository.save(profile)

    def bind(self, actor: ActorRef, source: MessageSource, card_id: str) -> CharacterCard:
        profile = self.repository.load(actor)
        card = self.get(actor, card_id)
        profile.bindings[source.key] = card.card_id
        self.repository.save(profile)
        return card

    def bind_global(self, actor: ActorRef, card_id: str) -> CharacterCard:
        profile = self.repository.load(actor)
        card = self.get(actor, card_id)
        profile.bindings["global"] = card.card_id
        self.repository.save(profile)
        return card

    def unbind(self, actor: ActorRef, source: MessageSource | None = None) -> None:
        profile = self.repository.load(actor)
        scope = "global" if source is None else source.key
        profile.bindings.pop(scope, None)
        self.repository.save(profile)

    def resolve(self, context: MessageContext) -> CharacterCard | None:
        profile = self.repository.load(context.actor)
        card_id = profile.bindings.get(context.source.key) or profile.bindings.get("global")
        return profile.cards.get(card_id) if card_id is not None else None


class NicknameService:
    def __init__(self, repository: ProfileRepository) -> None:
        self.repository = repository

    def set(
        self,
        actor: ActorRef,
        name: str,
        source: MessageSource | None = None,
    ) -> str:
        profile = self.repository.load(actor)
        key = "global" if source is None else source.key
        profile.nicknames[key] = _clean_name(name, "nickname")
        self.repository.save(profile)
        return profile.nicknames[key]

    def remove(self, actor: ActorRef, source: MessageSource | None = None) -> bool:
        profile = self.repository.load(actor)
        key = "global" if source is None else source.key
        removed = profile.nicknames.pop(key, None) is not None
        self.repository.save(profile)
        return removed

    def clear(self, actor: ActorRef) -> int:
        profile = self.repository.load(actor)
        count = len(profile.nicknames)
        profile.nicknames.clear()
        self.repository.save(profile)
        return count

    def resolve(self, context: MessageContext) -> str:
        profile = self.repository.load(context.actor)
        for candidate in (
            profile.nicknames.get(context.source.key),
            profile.nicknames.get("global"),
            context.source_nickname,
            context.account_nickname,
        ):
            if candidate and candidate.strip():
                return candidate.strip()
        return f"陌生人({context.actor.user_id})"


class SettingService:
    def __init__(self, repository: ProfileRepository) -> None:
        self.repository = repository

    def get(self, actor: ActorRef, key: str, default: Any = None) -> Any:
        return self.repository.load(actor).settings.get(key, default)

    def set(self, actor: ActorRef, key: str, value: Any) -> Any:
        profile = self.repository.load(actor)
        profile.settings[str(key)] = value
        self.repository.save(profile)
        return value

    def remove(self, actor: ActorRef, key: str) -> bool:
        profile = self.repository.load(actor)
        existed = str(key) in profile.settings
        profile.settings.pop(str(key), None)
        self.repository.save(profile)
        return existed


@dataclass(slots=True)
class IdentityServices:
    repository: ProfileRepository
    characters: CharacterService = field(init=False)
    nicknames: NicknameService = field(init=False)
    settings: SettingService = field(init=False)

    def __post_init__(self) -> None:
        self.characters = CharacterService(self.repository)
        self.nicknames = NicknameService(self.repository)
        self.settings = SettingService(self.repository)
