from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

import re
import sys

_BUNDLED_SOURCE = Path(__file__).resolve().parents[1] / "src"
if _BUNDLED_SOURCE.is_dir() and str(_BUNDLED_SOURCE) not in sys.path:
    sys.path.insert(0, str(_BUNDLED_SOURCE))

from trpg_dice import (
    ActorRef,
    CommandResponse,
    CommandRouter,
    DiceEngine,
    DiceError,
    IdentityServices,
    MessageContext,
    MessageSource,
    ProfileRepository,
    UnknownCommandError,
)
from trpg_dice.storage import JsonStore


DEFAULT_PREFIXES = (".", "。")
DICE_COMMAND_PATTERN = (
    r"(?i)^[.。]+\s*(?!rdc|rdx|rsr|rnc|rfc|rbh|rws)(?:"
    r"bot(?=\s+(?:on|off)\s*$)|"
    r"help|drawh?|name|nnn?|ob|setcoc|set|dnd|pc|init|ww?|me|jrrp|welcome|"
    r"deck|rules?|log|game|ti|li|en|str|"
    r"ak(?:[#=+\-][^\s]*)?|"
    r"coc[67]?s?[\dd]*|"
    r"(?:r(?:oll|h|s|d|b|p)?|rc[bp]?|ra|ri|st|sc)"
    r"(?:[\dDdFfKkBbPpXx+*/().#_\-]|[^\x00-\x7f\s])*"
    r")(?=\s|$)(?:\s[\s\S]*)?$"
)
_DICE_COMMAND_RE = re.compile(DICE_COMMAND_PATTERN)
SendText = Callable[[str, str], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class DiceDispatch:
    """The result of adapting one MaiBot message."""

    handled: bool
    stream_id: str = ""
    reply: str = ""
    response: CommandResponse | None = None


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _raw_text(message: Any) -> str:
    raw_message = _value(message, "raw_message")
    components = _value(raw_message, "components", raw_message)
    if not isinstance(components, (list, tuple)):
        return ""

    text_parts: list[str] = []
    for component in components:
        component_type = _text(_value(component, "type")).casefold()
        if component_type != "text":
            continue
        data = _value(component, "data")
        if isinstance(data, Mapping):
            data = data.get("text", "")
        if data is not None:
            text_parts.append(_text(data))
    return "".join(text_parts)


class DiceCommandAdapter:
    """Translate MaiBot message payloads into the dice core's input models.

    MaiBot 2.x sends serialized ``message`` dictionaries to event handlers. The
    fallback keyword arguments keep the adapter usable with older SDK event
    payloads that expose ``plain_text`` and identity fields directly.
    """

    def __init__(
        self,
        data_dir: str | Path,
        *,
        prefixes: tuple[str, ...] | list[str] = DEFAULT_PREFIXES,
        platforms: tuple[str, ...] | list[str] | None = ("qq",),
        router: CommandRouter | None = None,
    ) -> None:
        normalized_prefixes = tuple(
            dict.fromkeys(str(prefix) for prefix in prefixes if str(prefix))
        )
        if not normalized_prefixes:
            raise ValueError("at least one command prefix is required")
        self.prefixes = normalized_prefixes
        self._bot_state_store = JsonStore(data_dir)
        self._bot_state_path = "config/bot_state.json"
        state = self._bot_state_store.read(self._bot_state_path) or {}
        disabled_groups = state.get("disabled_groups", {})
        if not isinstance(disabled_groups, Mapping):
            disabled_groups = {}
        self._disabled_groups = {
            str(group_key)
            for group_key, disabled in disabled_groups.items()
            if disabled
        }
        self.platforms = (
            None
            if platforms is None
            else frozenset(str(platform).casefold() for platform in platforms)
        )
        if router is None:
            identities = IdentityServices(ProfileRepository(data_dir))
            router = CommandRouter(DiceEngine(identities))
        self.router = router

    def dispatch(self, message: Any = None, **kwargs: Any) -> DiceDispatch:
        """Process one event payload without sending a platform message."""

        payload = self._normalize_payload(message, kwargs)
        text = payload["text"].strip()
        if not text.startswith(self.prefixes):
            return DiceDispatch(handled=False)

        platform = payload["platform"] or "qq"
        if self.platforms is not None and platform.casefold() not in self.platforms:
            return DiceDispatch(handled=False)

        stream_id = payload["stream_id"]
        command_text = self._normalize_prefix(text)
        if _DICE_COMMAND_RE.fullmatch(command_text) is None:
            return DiceDispatch(handled=False)
        bot_operation = self._bot_operation(command_text)
        if bot_operation is not None:
            return self._dispatch_bot(
                payload,
                platform,
                stream_id,
                bot_operation,
                self._build_context(payload, platform),
            )
        if payload["group_id"] and self._group_key(platform, payload["group_id"]) in self._disabled_groups:
            return DiceDispatch(handled=False)
        context = self._build_context(payload, platform)
        try:
            response = self.router.execute(context, command_text)
        except UnknownCommandError:
            return DiceDispatch(handled=False)
        except DiceError as error:
            return DiceDispatch(
                handled=True,
                stream_id=stream_id,
                reply=f"骰子指令错误：{error}",
            )
        return DiceDispatch(
            handled=True,
            stream_id=stream_id,
            reply=response.rendered,
            response=response,
        )

    def _dispatch_bot(
        self,
        payload: Mapping[str, str],
        platform: str,
        stream_id: str,
        operation: str,
        context: MessageContext,
    ) -> DiceDispatch:
        if not payload["group_id"]:
            return DiceDispatch(
                handled=True,
                stream_id=stream_id,
                reply=self.router.messages.render(
                    "strBotPrivate", self._message_values(context)
                ),
            )
        group_key = self._group_key(platform, payload["group_id"])
        disabled = group_key in self._disabled_groups
        if operation == "off":
            changed = not disabled
            self._disabled_groups.add(group_key)
            reply = self.router.messages.render(
                "strBotOff" if changed else "strBotOffAlready",
                self._message_values(context),
            )
        else:
            changed = disabled
            self._disabled_groups.discard(group_key)
            reply = self.router.messages.render(
                "strBotOn" if changed else "strBotOnAlready",
                self._message_values(context),
            )
        self._save_bot_state()
        return DiceDispatch(
            handled=True,
            stream_id=stream_id,
            reply=reply,
            response=CommandResponse(
                "bot",
                operation,
                {"enabled": operation == "on", "changed": changed},
                reply,
                {"operation": operation, "group_id": payload["group_id"]},
            ),
        )

    @staticmethod
    def _bot_operation(command_text: str) -> str | None:
        match = re.fullmatch(r"\.bot\s+(on|off)\s*", command_text, flags=re.IGNORECASE)
        return match.group(1).casefold() if match else None

    @staticmethod
    def _group_key(platform: str, group_id: str) -> str:
        return f"{platform.casefold()}:{group_id}"

    def _save_bot_state(self) -> None:
        self._bot_state_store.write(
            self._bot_state_path,
            {"disabled_groups": {group_key: True for group_key in sorted(self._disabled_groups)}},
        )

    def _message_values(self, context: MessageContext) -> dict[str, str]:
        nickname = context.account_nickname or context.actor.user_id
        return {
            "nick": nickname,
            "pc": nickname,
            "self": self.router.messages.get("self"),
            "uid": context.actor.user_id,
            "platform": context.actor.platform,
            "source": context.source.source_id,
        }

    async def handle(
        self,
        message: Any = None,
        *,
        send_text: SendText,
        **kwargs: Any,
    ) -> DiceDispatch:
        """Process a message and send a reply when it is a dice command."""

        dispatch = self.dispatch(message, **kwargs)
        if dispatch.handled and dispatch.stream_id:
            await send_text(dispatch.reply, dispatch.stream_id)
        return dispatch

    def _normalize_payload(self, message: Any, kwargs: Mapping[str, Any]) -> dict[str, str]:
        message_info = _value(message, "message_info", {}) or {}
        user_info = _value(message_info, "user_info", {}) or {}
        group_info = _value(message_info, "group_info")
        additional_config = _value(message_info, "additional_config", {}) or {}

        text = _text(
            _value(message, "processed_plain_text")
            or _value(message, "plain_text")
            or kwargs.get("plain_text")
            or kwargs.get("text")
            or _raw_text(message)
        )
        platform = _text(_value(message, "platform") or kwargs.get("platform"))
        user_id = _text(
            _value(user_info, "user_id")
            or _value(message, "user_id")
            or kwargs.get("user_id")
        )
        user_nickname = _text(
            _value(user_info, "user_nickname")
            or _value(message, "user_nickname")
            or kwargs.get("user_nickname")
        )
        user_cardname = _text(
            _value(user_info, "user_cardname")
            or _value(message, "user_cardname")
            or kwargs.get("user_cardname")
        )
        group_id = _text(
            _value(group_info, "group_id")
            or _value(message, "group_id")
            or kwargs.get("group_id")
        )
        group_name = _text(_value(group_info, "group_name") or kwargs.get("group_name"))
        stream_id = _text(
            _value(message, "session_id")
            or kwargs.get("stream_id")
            or kwargs.get("chat_id")
        )
        if not stream_id:
            stream_id = group_id or user_id
        if not platform:
            platform = "qq"
        if not user_id:
            user_id = "unknown-user"

        account_id = _text(
            kwargs.get("account_id")
            or _value(additional_config, "account_id")
            or _value(additional_config, "bot_account_id")
        )
        return {
            "text": text,
            "platform": platform,
            "user_id": user_id,
            "user_nickname": user_nickname,
            "user_cardname": user_cardname,
            "group_id": group_id,
            "group_name": group_name,
            "stream_id": stream_id,
            "account_id": account_id,
        }

    @staticmethod
    def _build_context(payload: Mapping[str, str], platform: str) -> MessageContext:
        actor = ActorRef(platform, payload["user_id"])
        if payload["group_id"]:
            source = MessageSource(platform, "group", payload["group_id"])
        else:
            source = MessageSource(platform, "private", payload["user_id"])
        return MessageContext(
            actor,
            source,
            account_nickname=payload["user_nickname"] or payload["user_id"],
            source_nickname=payload["user_cardname"] or None,
        )

    def _normalize_prefix(self, text: str) -> str:
        for prefix in self.prefixes:
            if text.startswith(prefix):
                return text if prefix == "." else "." + text[len(prefix) :]
        return text
