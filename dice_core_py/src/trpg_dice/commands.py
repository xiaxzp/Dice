from __future__ import annotations

import re
from difflib import get_close_matches
from datetime import date
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from .engine import DiceEngine
from .errors import CommandError, IdentityError, UnknownCommandError
from .models import (
    CheckResult,
    MessageContext,
    RollRequest,
    RollResponse,
)
from .profiles import CharacterCard, IdentityServices
from .roller import DiceRoller
from .session import DiceSession
from .special import DeckEntry


@dataclass(frozen=True, slots=True)
class CommandRequest:
    """A platform-neutral command input supplied by an adapter."""

    context: MessageContext
    text: str


@dataclass(frozen=True, slots=True)
class CommandResponse:
    """Structured output from one routed command; no message is sent here."""

    command: str
    args: str
    result: Any
    rendered: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "args": self.args,
            "result": _to_jsonable(self.result),
            "rendered": self.rendered,
            "metadata": _to_jsonable(self.metadata),
        }


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class _ParsedCommand:
    command: str
    args: str
    metadata: dict[str, Any]


class CommandRouter:
    """Dispatch dot-style TRPG commands without knowing any chat platform.

    The router intentionally receives the complete command text as an input
    parameter. An adapter can therefore pass QQ, Discord, HTTP, or CLI text
    through the same entry point without putting transport logic in this
    module.
    """

    def __init__(self, engine: DiceEngine, session: DiceSession | None = None) -> None:
        self.engine = engine
        self.identities: IdentityServices = engine.identities
        self.roller: DiceRoller = engine.roller
        self.session = session
        self._sessions: dict[str, DiceSession] = {}
        self._handlers: dict[str, Callable[[MessageContext, str, dict[str, Any]], CommandResponse]] = {
            "r": self._handle_roll,
            "ob": self._handle_observer,
            "set": self._handle_set,
            "name": self._handle_name,
            "nn": self._handle_nickname,
            "nnn": self._handle_nickname,
            "rc": self._handle_check,
            "coc": self._handle_coc,
            "dnd": self._handle_dnd,
            "pc": self._handle_pc,
            "st": self._handle_status,
            "setcoc": self._handle_setcoc,
            "sc": self._handle_sanity,
            "ti": self._handle_madness,
            "li": self._handle_madness,
            "en": self._handle_growth,
            "ri": self._handle_initiative,
            "init": self._handle_init,
            "w": self._handle_pool,
            "ww": self._handle_pool,
            "me": self._handle_action,
            "jrrp": self._handle_jrrp,
            "welcome": self._handle_welcome,
            "draw": self._handle_draw,
            "deck": self._handle_deck,
            "ak": self._handle_ank,
            "rules": self._handle_rules,
            "log": self._handle_log,
            "help": self._handle_help,
        }
        for name in (
            "bot", "reply", "dismiss", "authorize", "send", "group",
            "rdc", "rdx", "rsr", "rnc", "rfc", "rbh", "rws",
        ):
            self._handlers[name] = self._handle_adapter_boundary

    def execute(self, context: MessageContext, text: str) -> CommandResponse:
        return self.dispatch(CommandRequest(context=context, text=text))

    def dispatch(self, request: CommandRequest) -> CommandResponse:
        parsed = self._parse(request.text)
        handler = self._handlers.get(parsed.command)
        if handler is None:
            raise UnknownCommandError(f"unknown command: {parsed.command}")
        metadata = dict(parsed.metadata)
        metadata.setdefault("command", parsed.command)
        return handler(request.context, parsed.args, metadata)

    def register(
        self,
        name: str,
        handler: Callable[[MessageContext, str, dict[str, Any]], CommandResponse],
    ) -> None:
        normalized = name.strip().casefold()
        if not normalized or not normalized.isidentifier():
            raise CommandError("command name must be a non-empty identifier")
        self._handlers[normalized] = handler

    @staticmethod
    def _parse(text: str) -> _ParsedCommand:
        if not isinstance(text, str) or not text.strip():
            raise CommandError("command text must not be empty")
        body = text.strip()
        if body[0] not in ".。．!！":
            raise CommandError("command must start with '.', '。', '．', '!', or '！'")
        body = body[1:].lstrip()
        if not body:
            raise CommandError("command name is missing")
        lower = body.casefold()

        if lower == "help" or lower.startswith("help "):
            return _ParsedCommand("help", body[4:].strip(), {})
        if lower.startswith("coc6"):
            return _ParsedCommand("coc", "6" + body[4:], {})
        if lower.startswith("coc"):
            return _ParsedCommand("coc", body[3:].strip(), {})
        if lower.startswith("setcoc"):
            return _ParsedCommand("setcoc", body[6:].strip(), {})
        if lower == "drawh" or lower.startswith("drawh "):
            return _ParsedCommand("draw", body[5:].strip(), {"hidden": True})
        if lower.startswith("ak#") or lower.startswith("ak+") or lower.startswith("ak-") or lower.startswith("ak="):
            operation = lower[2]
            value = body[3:].strip() if len(body) > 3 else ""
            return _ParsedCommand("ak", f"{operation} {value}".strip(), {})
        for command in ("authorize", "dismiss", "reply", "welcome", "rules", "group", "jrrp", "init", "name", "send", "deck", "draw", "dnd", "pc", "ob", "set", "nnn", "nn", "log", "bot", "me", "ti", "li", "en", "ww", "w", "ak"):
            if lower == command or lower.startswith(command + " "):
                return _ParsedCommand(command, body[len(command):].strip(), {"detailed": command == "ww"})
        for command in ("rdc", "rdx", "rsr", "rnc", "rfc", "rbh", "rws"):
            if lower.startswith(command):
                return _ParsedCommand(command, body[len(command):].strip(), {})
        if lower.startswith("st"):
            return _ParsedCommand("st", body[2:].strip(), {})
        if lower.startswith("sc"):
            return _ParsedCommand("sc", body[2:].strip(), {})
        if lower.startswith("ri"):
            return _ParsedCommand("ri", body[2:].strip(), {})
        if lower.startswith("rcp"):
            return _ParsedCommand("rc", body[3:].strip(), {"mode": "penalty"})
        if lower.startswith("ra"):
            return _ParsedCommand("rc", body[2:].strip(), {"mode": "bonus"})
        if lower.startswith("rc"):
            return _ParsedCommand("rc", body[2:].strip(), {"mode": "normal"})
        if lower.startswith("rb"):
            count = body[2:].strip() or "1"
            return _ParsedCommand("r", "b" + count, {"hidden": False})
        if lower.startswith("rp"):
            count = body[2:].strip() or "1"
            return _ParsedCommand("r", "p" + count, {"hidden": False})
        if lower.startswith("rh"):
            return _ParsedCommand("r", body[2:].strip(), {"hidden": True})
        if lower.startswith("rs"):
            return _ParsedCommand("r", body[2:].strip(), {"short": True})
        if lower.startswith("roll"):
            return _ParsedCommand("r", body[4:].strip(), {})
        if lower.startswith("r"):
            return _ParsedCommand("r", body[1:].strip(), {})
        command, _, args = body.partition(" ")
        if command.isidentifier():
            return _ParsedCommand(command.casefold(), args.strip(), {})
        raise UnknownCommandError(f"unknown command: {command}")

    def _handle_roll(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        repeat, body = self._split_repeat(args)
        if repeat == 1:
            suffix_match = re.match(r"^(.*?)#(?:\s+(.*))?$", body, flags=re.DOTALL)
            if suffix_match:
                body = suffix_match.group(1).strip()
                if suffix_match.group(2):
                    body = f"{body} {suffix_match.group(2).strip()}"
        if ":" in body or "：" in body:
            reason, expression = re.split(r"[:：]", body, maxsplit=1)
            expression, reason = expression.strip(), reason.strip() or None
        else:
            expression, reason = self._split_roll_reason(body)
        if expression.casefold() in {"b", "p"}:
            expression = expression.upper() + "1"
        card = self.identities.characters.resolve(context)
        if card is not None:
            stored_expression = card.attributes.get(expression)
            if isinstance(stored_expression, str):
                expression = stored_expression
            elif reason and not self._can_normalize(expression):
                candidate, separator, trailing_reason = reason.partition(" ")
                stored_expression = card.attributes.get(candidate)
                if isinstance(stored_expression, str):
                    expression = stored_expression
                    reason = trailing_reason or candidate
        if reason and not self._can_normalize(expression):
            original_expression = expression
            if self._can_normalize(reason):
                expression, reason = reason, original_expression
            else:
                candidate, _, trailing_reason = reason.partition(" ")
                if self._can_normalize(candidate):
                    expression = candidate
                    reason = original_expression + (f" {trailing_reason}" if trailing_reason else "")
        responses = [
            self.engine.roll(RollRequest(context, expression, reason))
            for _ in range(repeat)
        ]
        result: RollResponse | list[RollResponse] = responses[0] if repeat == 1 else responses
        rendered = "\n".join(self._render_roll(response, metadata) for response in responses)
        response_metadata = dict(metadata)
        response_metadata.update({"repeat": repeat, "reason": reason})
        return CommandResponse("r", args, result, rendered, response_metadata)

    def _handle_check(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        repeat, body = self._split_repeat(args)
        if not body:
            raise CommandError(".rc requires a skill or target")
        hidden = metadata.get("hidden", False) or body.startswith("_")
        if hidden:
            body = body[1:].lstrip()
        if body[:1].casefold() in {"b", "p"} and (len(body) == 1 or body[1].isspace()):
            metadata = dict(metadata)
            metadata["mode"] = "bonus" if body[0].casefold() == "b" else "penalty"
            body = body[1:].lstrip()
        auto_success = body.startswith("自动成功")
        if auto_success:
            body = body[4:].lstrip()
        difficulty, body = self._read_difficulty(body)
        skill_expression, explicit_target, reason = self._split_check_args(body)
        card = self.identities.characters.resolve(context)
        attributes = card.attributes if card else {}
        target_expression = explicit_target or skill_expression
        target = self._evaluate_attribute_expression(target_expression, attributes)
        target = max(1, int(target * difficulty))
        mode = metadata.get("mode", "normal")
        bonus_dice = 1 if mode == "bonus" else 0
        penalty_dice = 1 if mode == "penalty" else 0
        rule = int(self._session_for(context).data.get("coc_rule", 0))
        checks = [
            self.roller.coc_check(
                target,
                bonus_dice=bonus_dice,
                penalty_dice=penalty_dice,
                rule=rule,
            )
            for _ in range(repeat)
        ]
        if auto_success:
            checks = [
                check
                if check.success or check.success_level == "fumble"
                else replace(check, success_level="regular_success")
                for check in checks
            ]
        result: CheckResult | list[CheckResult] = checks[0] if repeat == 1 else checks
        rendered = "\n".join(self._render_check(check, hidden) for check in checks)
        response_metadata = dict(metadata)
        response_metadata.update(
            {
                "skill": skill_expression,
                "target": target,
                "difficulty": difficulty,
                "hidden": hidden,
                "reason": reason,
                "repeat": repeat,
                "rule": rule,
                "auto_success": auto_success,
            }
        )
        return CommandResponse("rc", args, result, rendered, response_metadata)

    def _handle_coc(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        compact = "".join(args.casefold().split())
        variant = 7
        if compact.startswith("6"):
            variant, compact = 6, compact[1:]
        elif compact.startswith("7"):
            compact = compact[1:]
        detailed = "d" in compact
        compact = compact.replace("d", "")
        count = int(compact) if compact else 1
        if not 1 <= count <= 10:
            raise CommandError(".coc generation count must be in 1..10")

        display_name = self.identities.nicknames.resolve(context)
        cards: list[CharacterCard] = []
        for index in range(count):
            attributes = self._generate_coc_attributes(variant)
            name = display_name if index == 0 else f"{display_name} {index + 1}"
            name = self._unique_card_name(context, name)
            card = self.identities.characters.create(
                context.actor,
                name,
                system=f"COC{variant}",
                attributes=attributes,
            )
            if index == 0:
                self.identities.characters.bind(context.actor, context.source, card.card_id)
            cards.append(card)
        result: CharacterCard | list[CharacterCard] = cards[0] if count == 1 else cards
        rendered = "\n".join(self._render_card(card, detailed) for card in cards)
        response_metadata = dict(metadata)
        response_metadata.update({"variant": variant, "detailed": detailed, "count": count})
        return CommandResponse("coc", args, result, rendered, response_metadata)

    def _handle_status(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        body = args.strip()
        card = self.identities.characters.resolve(context)
        if body.casefold() == "show" or body.casefold().startswith("show "):
            if card is None:
                result: dict[str, Any] = {}
            else:
                requested = body[4:].strip()
                if not requested:
                    result = card.attributes
                else:
                    key = self._attribute_key(card.attributes, requested)
                    result = {} if key not in card.attributes else {requested: card.attributes[key]}
            return CommandResponse("st", args, result, self._render_attributes(result))

        card = card or self._ensure_card(context)
        if body.casefold() == "clr":
            updated = self.identities.characters.update(context.actor, card.card_id, attributes={})
            return CommandResponse("st", args, updated, "属性已清空")
        if body.casefold().startswith("del "):
            names = body[4:].split()
            attributes = dict(card.attributes)
            for name in names:
                attributes.pop(self._attribute_key(attributes, name), None)
            updated = self.identities.characters.update(
                context.actor, card.card_id, attributes=attributes
            )
            return CommandResponse("st", args, updated, f"已删除属性：{' '.join(names)}")
        if not body:
            return CommandResponse("st", args, card.attributes, self._render_attributes(card.attributes))

        attributes = dict(card.attributes)
        changed: dict[str, Any] = {}
        for token in body.split():
            expression_attribute = token.startswith("&")
            name, operator, value_expression = self._parse_attribute_assignment(token)
            current_key = self._attribute_key(attributes, name)
            if expression_attribute:
                if operator != "=":
                    raise CommandError("expression attributes only support '='")
                attributes[name] = value_expression
                changed[name] = value_expression
                continue
            value = self._evaluate_attribute_expression(value_expression, attributes)
            if operator in {"+", "-"}:
                current = attributes.get(current_key, 0)
                if not isinstance(current, (int, float)):
                    raise IdentityError(f"attribute {name!r} is not numeric")
                value = current + value if operator == "+" else current - value
            attributes[name if current_key == name else current_key] = value
            changed[name] = value
        updated = self.identities.characters.update(
            context.actor, card.card_id, attributes=attributes
        )
        return CommandResponse("st", args, updated, self._render_attributes(changed))

    def _handle_sanity(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        parts = args.split()
        if not parts or "/" not in parts[0]:
            raise CommandError(".sc requires success_loss/failure_loss")
        success_loss, failure_loss = parts[0].split("/", 1)
        card = self.identities.characters.resolve(context) or self._ensure_card(context)
        current_text = parts[1] if len(parts) > 1 else None
        reason = None
        if current_text and not self._is_attribute_or_expression(current_text, card.attributes):
            reason = " ".join(parts[1:])
            current_text = None
        current = (
            self._evaluate_attribute_expression(current_text, card.attributes)
            if current_text
            else self._read_first_numeric(card.attributes, ("san", "理智"))
        )
        if current is None:
            raise CommandError(".sc requires current san or 理智")
        roll = self.roller.roll("d100")
        success = roll.total <= current
        loss = self._evaluate_attribute_expression(
            success_loss if success else failure_loss, card.attributes
        )
        remaining = current - loss
        attributes = dict(card.attributes)
        san_key = self._attribute_key(attributes, "san")
        if san_key == "san" and "理智" in attributes:
            san_key = "理智"
        attributes[san_key] = remaining
        updated = self.identities.characters.update(
            context.actor, card.card_id, attributes=attributes
        )
        result = {
            "roll": roll,
            "current": current,
            "success": success,
            "loss": loss,
            "remaining": remaining,
            "card": updated,
        }
        rendered = f"{roll.render()} / {current} {'成功' if success else '失败'}，损失 {loss}，剩余 {remaining}"
        return CommandResponse("sc", args, result, rendered, {"reason": reason})

    def _handle_initiative(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        body = args.strip()
        offset = 0
        offset_match = re.match(r"^([+-]\d+)(?:\s+|$)(.*)$", body)
        if offset_match:
            offset = int(offset_match.group(1))
            body = offset_match.group(2).strip()
        repeat, body = self._split_repeat(body)
        name = self.identities.nicknames.resolve(context)
        expression = "d20"
        explicit_value: int | None = None
        if body:
            first, separator, rest = body.partition(" ")
            if self._is_initiative_expression(first):
                if first.casefold() == "2dk":
                    first = "2d20k1"
                name = rest.strip() or name
                if first.isdigit():
                    explicit_value = int(first)
                else:
                    expression = first
            else:
                name = body
        entries = []
        for index in range(repeat):
            value = (
                explicit_value
                if explicit_value is not None
                else self.roller.roll(expression).total
            )
            entries.append(
                {
                    "name": name if repeat == 1 else f"{name}{index + 1}",
                    "value": value + offset,
                }
            )
        session = self._session_for(context)
        session.data["initiative"] = list(session.data.get("initiative", [])) + entries
        entries.sort(key=lambda item: item["value"], reverse=True)
        rendered = "\n".join(f"{entry['name']}: {entry['value']}" for entry in entries)
        return CommandResponse(
            "ri",
            args,
            entries,
            rendered,
            {"offset": offset, "repeat": repeat, "expression": expression, "explicit_value": explicit_value},
        )

    @staticmethod
    def _is_initiative_expression(value: str) -> bool:
        return bool(re.fullmatch(r"[0-9dDfFkKbBpPxXaA+*/().-]+", value))

    def _handle_help(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        commands = {
            "r": "普通骰：.r [表达式] [原因]",
            "ob": "旁观状态：.ob join/exit/list/clr/on/off",
            "set": "默认骰面数：.set [1..1000]",
            "name": "随机昵称：.name [cn|jp|en] [数量]",
            "nn": "称呼：.nn [昵称|del|clr]，.nnn [cn|jp|en]",
            "rc": "COC检定：.rc [困难/极难][属性或表达式] [成功率]",
            "ra/rcp": "奖励/惩罚检定",
            "coc": "COC人物卡生成：.coc[6] [数量] [d]",
            "dnd": "DND人物属性生成：.dnd [数量]",
            "pc": "人物卡管理：.pc new/tag/show/nn/cpy/del/list/grp/build/redo/clr/stat",
            "st": "属性记录：.st 属性:值、.st show、.st del、.st clr",
            "setcoc": "COC房规：.setcoc [0..6|show|clr]",
            "sc": "San检定：.sc 成功损失/失败损失 [当前San]",
            "ti/li": "临时/总结疯狂症状",
            "en": "成长检定：.en [技能] [当前值]",
            "ri/init": "先攻：.ri[加值] [数量#]名称，.init[/clr]",
            "w/ww": "骰池：.w [数量]a[加骰阈值]",
            "me": "第三人称动作：.me [动作]",
            "jrrp": "今日人品：.jrrp [on|off]",
            "welcome": "欢迎词：.welcome [文本|show|clr]",
            "draw/deck": "抽牌和牌堆管理",
            "ak": "安价分歧：.ak new/add/del/get/show/clr",
            "rules": "规则查询和默认规则：.rules [规则:]词条/set [规则]",
            "log": "日志状态：.log new/on/off/end",
            "bot": "平台适配器：.bot on/off",
            "reply": "平台适配器：.reply on/off",
            "dismiss": "平台适配器：.dismiss",
            "authorize": "平台适配器：!authorize",
            "send": "平台适配器：.send",
            "group": "平台适配器：.group",
            "rdc": "扩展指令，由平台/扩展适配器提供",
            "rdx": "扩展指令，由平台/扩展适配器提供",
            "rsr": "扩展指令，由平台/扩展适配器提供",
            "rnc": "扩展指令，由平台/扩展适配器提供",
            "rfc": "扩展指令，由平台/扩展适配器提供",
            "rbh": "扩展指令，由平台/扩展适配器提供",
            "rws": "扩展指令，由平台/扩展适配器提供",
        }
        if args.strip():
            key = args.strip().casefold().lstrip(".")
            if key in commands:
                result = {key: commands[key]}
            else:
                suggestions = get_close_matches(key, commands, n=1, cutoff=0.5)
                result = {suggestions[0]: commands[suggestions[0]]} if suggestions else {}
        else:
            result = commands
        rendered = "\n".join(f".{key}: {value}" for key, value in result.items())
        return CommandResponse("help", args, result, rendered)

    def _session_for(self, context: MessageContext) -> DiceSession:
        if self.session is not None:
            return self.session
        key = context.source.key
        if key not in self._sessions:
            self._sessions[key] = DiceSession(key, rng=self.roller.rng)
        return self._sessions[key]

    def _handle_observer(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        operation = args.strip().casefold() or "join"
        if operation == "join":
            changed = session.add_observer(context.actor)
            result = {"joined": changed, "observers": [item.to_dict() for item in session.observers]}
        elif operation == "exit":
            changed = context.actor in session.observers
            session.observers.discard(context.actor)
            result = {"exited": changed, "observers": [item.to_dict() for item in session.observers]}
        elif operation == "list":
            result = [item.to_dict() for item in sorted(session.observers, key=lambda item: item.key)]
        elif operation == "clr":
            session.observers.clear()
            result = []
        elif operation in {"on", "off"}:
            session.data["observer_enabled"] = operation == "on"
            result = {"enabled": session.data["observer_enabled"]}
        else:
            raise CommandError(".ob expects join, exit, list, clr, on, or off")
        return CommandResponse("ob", args, result, str(result), {"operation": operation})

    def _handle_set(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        value = args.strip()
        if not value:
            self.identities.settings.remove(context.actor, "default_dice")
            return CommandResponse("set", args, {"default_sides": 100}, "默认骰已重置")
        try:
            sides = int(value)
        except ValueError as error:
            raise CommandError(".set expects a number between 1 and 1000") from error
        if not 1 <= sides <= 1000:
            raise CommandError(".set expects a number between 1 and 1000")
        card = self.identities.characters.resolve(context)
        if card is None:
            self.identities.settings.set(context.actor, "default_dice", f"d{sides}")
        else:
            attributes = dict(card.attributes)
            attributes["__DefaultDice"] = f"d{sides}"
            self.identities.characters.update(context.actor, card.card_id, attributes=attributes)
        return CommandResponse("set", args, {"default_sides": sides}, f"默认骰：D{sides}")

    def _random_names(self, kind: str, count: int) -> list[str]:
        pools = {
            "cn": ("林墨", "沈青", "顾言", "白宁", "苏禾"),
            "jp": ("佐藤", "山田", "千夏", "凛", "春日"),
            "en": ("Alice", "Morgan", "Robin", "Evan", "Alex"),
        }
        selected = pools.get(kind, pools["en"] + pools["cn"] + pools["jp"])
        return [selected[self.roller.randint(0, len(selected) - 1)] for _ in range(count)]

    def _handle_name(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        parts = args.split()
        kind = next((part.casefold() for part in parts if part.casefold() in {"cn", "jp", "en"}), "all")
        count_text = next((part for part in parts if part.isdigit()), "1")
        count = int(count_text)
        if not 1 <= count <= 20:
            raise CommandError(".name count must be in 1..20")
        result = self._random_names(kind, count)
        return CommandResponse("name", args, result, "、".join(result), {"kind": kind, "count": count})

    def _handle_nickname(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        body = args.strip()
        if metadata.get("command") == "nnn":
            body = self._random_names(body.casefold() or "all", 1)[0]
        if body.casefold() == "clr":
            result = self.identities.nicknames.clear(context.actor)
            return CommandResponse("nn", args, result, "已清除全部称呼")
        if body.casefold() == "del" or not body:
            source = None if context.source.kind == "private" else context.source
            result = self.identities.nicknames.remove(context.actor, source)
            return CommandResponse("nn", args, result, "已删除当前称呼")
        if body.casefold() == "nnn" or body.casefold().startswith("nnn "):
            kind = body[3:].strip().casefold() or "all"
            body = self._random_names(kind, 1)[0]
        elif body.casefold().startswith("n "):
            body = body[2:].strip()
        source = None if context.source.kind == "private" else context.source
        result = self.identities.nicknames.set(context.actor, body, source)
        return CommandResponse("nn", args, result, f"称呼已设置为：{result}")

    def _handle_dnd(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        count = int(args.strip() or "1")
        if not 1 <= count <= 10:
            raise CommandError(".dnd generation count must be in 1..10")
        display_name = self.identities.nicknames.resolve(context)
        cards = []
        for index in range(count):
            attributes = {name: self.roller.roll("4d6k3").total for name in ("力量", "敏捷", "体质", "智力", "感知", "魅力")}
            name = self._unique_card_name(context, display_name if index == 0 else f"{display_name} {index + 1}")
            card = self.identities.characters.create(context.actor, name, system="DND", attributes=attributes)
            if index == 0:
                self.identities.characters.bind(context.actor, context.source, card.card_id)
            cards.append(card)
        result = cards[0] if count == 1 else cards
        return CommandResponse("dnd", args, result, "\n".join(self._render_card(card, False) for card in cards), {"count": count})

    def _handle_pc(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        parts = args.split(maxsplit=1)
        operation = parts[0].casefold() if parts else "show"
        value = parts[1].strip() if len(parts) == 2 else ""
        current = self.identities.characters.resolve(context)
        if operation == "new":
            name = value or self.identities.nicknames.resolve(context)
            card = self.identities.characters.create(context.actor, self._unique_card_name(context, name), system="COC7")
            return CommandResponse("pc", args, card, self._render_card(card, True))
        if operation == "list":
            cards = self.identities.characters.list(context.actor)
            return CommandResponse("pc", args, cards, "\n".join(self._render_card(card, False) for card in cards))
        if operation == "grp":
            profile = self.identities.repository.load(context.actor)
            result = dict(profile.bindings)
            return CommandResponse("pc", args, result, str(result))
        if operation == "show":
            card = self._card_by_ref(context, value) if value else current
            result = card.to_dict() if card else {}
            return CommandResponse("pc", args, result, self._render_card(card, True) if card else "无当前人物卡")
        if operation == "tag":
            if not value:
                source = None if context.source.kind == "private" else context.source
                self.identities.characters.unbind(context.actor, source)
                return CommandResponse("pc", args, {}, "已解除当前绑定")
            card = self._card_by_ref(context, value)
            if context.source.kind == "private":
                self.identities.characters.bind_global(context.actor, card.card_id)
            else:
                self.identities.characters.bind(context.actor, context.source, card.card_id)
            return CommandResponse("pc", args, card, f"已绑定：{card.name}")
        if operation == "clr":
            cards = self.identities.characters.list(context.actor)
            for card in cards:
                self.identities.characters.delete(context.actor, card.card_id)
            return CommandResponse("pc", args, len(cards), "人物卡已清空")
        if operation == "stat":
            return CommandResponse("pc", args, {}, "暂无掷骰统计")
        if operation == "cpy":
            if "=" not in value:
                raise CommandError(".pc cpy expects destination=source")
            destination, target = (item.strip() for item in value.split("=", 1))
            source = self._card_by_ref(context, target)
            card = self.identities.characters.create(
                context.actor,
                self._unique_card_name(context, destination),
                system=source.system,
                attributes=source.attributes,
            )
            return CommandResponse("pc", args, card, self._render_card(card, True))
        if operation in {"build", "redo"} and value:
            current = self._card_by_ref(context, value)
        if current is None:
            raise CommandError("no current character card")
        if operation == "nn":
            card = self.identities.characters.rename(context.actor, current.card_id, value)
            return CommandResponse("pc", args, card, f"已重命名：{card.name}")
        if operation == "del":
            card = self._card_by_ref(context, value) if value else current
            self.identities.characters.delete(context.actor, card.card_id)
            return CommandResponse("pc", args, {}, "人物卡已删除")
        if operation in {"build", "redo"}:
            attributes = {} if operation == "redo" else dict(current.attributes)
            attributes.update(self._generate_coc_attributes(7))
            card = self.identities.characters.update(context.actor, current.card_id, attributes=attributes)
            return CommandResponse("pc", args, card, self._render_card(card, True))
        raise CommandError(f"unknown .pc operation: {operation}")

    def _card_by_ref(self, context: MessageContext, reference: str) -> CharacterCard:
        normalized = reference.strip()
        if not normalized:
            raise CommandError("character card reference must not be empty")
        for card in self.identities.characters.list(context.actor):
            if card.card_id == normalized or card.name.casefold() == normalized.casefold():
                return card
        raise IdentityError(f"character card {reference!r} does not exist")

    def _handle_setcoc(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        value = args.strip().casefold()
        if value == "show" or not value:
            rule = int(session.data.get("coc_rule", 0))
            return CommandResponse("setcoc", args, rule, f"当前COC房规：{rule}")
        if value == "clr":
            session.data.pop("coc_rule", None)
            return CommandResponse("setcoc", args, 0, "已清除COC房规")
        try:
            rule = int(value)
        except ValueError as error:
            raise CommandError(".setcoc expects 0..6, show, or clr") from error
        if not 0 <= rule <= 6:
            raise CommandError(".setcoc rule must be in 0..6")
        session.data["coc_rule"] = rule
        return CommandResponse("setcoc", args, rule, f"COC房规已设置为：{rule}")

    def _handle_madness(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        temporary = metadata.get("command") == "ti"
        duration = "临时" if temporary else "总结"
        result = {"type": "temporary" if temporary else "indefinite", "duration": duration, "roll": self.roller.roll("d10").total}
        return CommandResponse("ti" if temporary else "li", args, result, f"{duration}疯狂症状：{result['roll']}")

    def _handle_growth(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        parts = args.split(maxsplit=2)
        if not parts:
            raise CommandError(".en requires a skill")
        skill = parts[0]
        card = self.identities.characters.resolve(context) or self._ensure_card(context)
        current = self._read_first_numeric(card.attributes, (skill,))
        if len(parts) > 1:
            current = self._evaluate_attribute_expression(parts[1], card.attributes)
        if current is None:
            raise CommandError(f"unknown skill: {skill}")
        roll = self.roller.roll("d100")
        success = roll.total > current
        updated_value = current + (self.roller.roll("1d10").total if success else 0)
        attributes = dict(card.attributes)
        key = self._attribute_key(attributes, skill)
        attributes[key] = updated_value
        updated = self.identities.characters.update(context.actor, card.card_id, attributes=attributes)
        result = {"skill": skill, "current": current, "roll": roll, "success": success, "value": updated_value, "card": updated}
        return CommandResponse("en", args, result, f"{skill}: {roll.total}/{current} {'成长' if success else '未成长'} -> {updated_value}")

    def _handle_init(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        if args.strip().casefold() == "clr":
            session.data["initiative"] = []
            return CommandResponse("init", args, [], "先攻列表已清空")
        entries = sorted(session.data.get("initiative", []), key=lambda item: item["value"], reverse=True)
        return CommandResponse("init", args, entries, "\n".join(f"{item['name']}: {item['value']}" for item in entries))

    def _handle_pool(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        body = args.strip()
        match = re.fullmatch(r"(\d+)\s*a\s*(\d+)?", body, flags=re.IGNORECASE)
        if match:
            count = int(match.group(1))
            target = int(match.group(2) or 8)
        else:
            card = self.identities.characters.resolve(context)
            if card is None:
                raise CommandError(".w expects [count]a[target] or a card expression")
            count = self._evaluate_attribute_expression(body, card.attributes)
            target = 8
        result = self.roller.pool(count, target=target)
        if metadata.get("detailed"):
            rendered = f"{list(result.rolls)} -> {result.successes}个成功"
        else:
            rendered = f"成功数：{result.successes}（{result.count}d{result.sides}，阈值{result.target}）"
        return CommandResponse("ww" if metadata.get("detailed") else "w", args, result, rendered, {"count": count, "target": target})

    def _handle_action(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        body = args.strip()
        if body.casefold() in {"on", "off"}:
            session = self._session_for(context)
            session.data["me_enabled"] = body.casefold() == "on"
            return CommandResponse("me", args, session.data["me_enabled"], f"me已{'启用' if session.data['me_enabled'] else '禁用'}")
        if not body:
            raise CommandError(".me requires an action")
        return CommandResponse("me", args, {"actor": context.actor.to_dict(), "action": body}, f"{self.identities.nicknames.resolve(context)}{body}")

    def _handle_jrrp(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        operation = args.strip().casefold()
        if operation in {"on", "off"}:
            session.data["jrrp_enabled"] = operation == "on"
            return CommandResponse("jrrp", args, session.data["jrrp_enabled"], f"jrrp已{operation}")
        key = f"jrrp:{date.today().isoformat()}:{context.actor.key}"
        values = session.data.setdefault("jrrp_values", {})
        if key not in values:
            values[key] = self.roller.randint(1, 100)
        return CommandResponse("jrrp", args, values[key], f"今日人品：{values[key]}")

    def _handle_welcome(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        body = args.strip()
        if body.casefold() == "clr":
            session.data.pop("welcome", None)
            return CommandResponse("welcome", args, None, "欢迎词已清空")
        if body.casefold() == "show" or not body:
            value = session.data.get("welcome")
            return CommandResponse("welcome", args, value, value or "未设置欢迎词")
        session.data["welcome"] = body
        return CommandResponse("welcome", args, body, f"欢迎词已设置：{body}")

    def _handle_draw(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        body = args.strip()
        hidden = metadata.get("hidden", False) or body.startswith("_") or body.casefold().startswith("h ")
        name = body[1:].strip() if body.startswith("_") else (body[1:].strip() if body.casefold().startswith("h ") else body)
        parts = name.split()
        if not parts or parts[0] not in session.decks:
            raise CommandError(f"deck {parts[0] if parts else ''!r} does not exist")
        count = int(parts[1]) if len(parts) > 1 else 1
        if count < 1:
            raise CommandError("draw count must be positive")
        entries = [session.draw(parts[0]) for _ in range(count)]
        result = [entry.value for entry in entries]
        return CommandResponse("draw", args, result if count > 1 else result[0], "、".join(result), {"hidden": hidden, "count": count})

    def _handle_deck(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        parts = args.strip().split(maxsplit=1)
        operation = parts[0].casefold() if parts else "show"
        value = parts[1].strip() if len(parts) == 2 else ""
        if operation == "show":
            if value and value in session.decks:
                result = {value: session.decks[value].to_dict()}
            else:
                result = {name: deck.remaining for name, deck in session.decks.items()}
            return CommandResponse("deck", args, result, str(result))
        if operation == "clr":
            session.decks.clear()
            return CommandResponse("deck", args, {}, "牌堆已清空")
        if operation == "reset":
            if value not in session.decks:
                raise CommandError(f"deck {value!r} does not exist")
            session.decks[value].reset()
            return CommandResponse("deck", args, session.decks[value].remaining, f"牌堆 {value} 已重置")
        if operation in {"new", "set"}:
            if "=" in value:
                name, raw_entries = (item.strip() for item in value.split("=", 1))
            else:
                name, raw_entries = value, ""
            if operation == "set" and raw_entries.casefold().startswith("range"):
                bounds = raw_entries.split()[1:]
                if len(bounds) != 2:
                    raise CommandError(".deck set name=range lower upper")
                lower, upper = (int(item) for item in bounds)
                if lower > upper:
                    raise CommandError("range lower must not exceed upper")
                entries = [DeckEntry(str(item)) for item in range(lower, upper + 1)]
            elif operation == "set" and raw_entries.casefold() == "member":
                return self._handle_adapter_boundary(context, args, {"command": "deck", "reason": "member list requires adapter input"})
            else:
                entries = [DeckEntry(item.strip()) for item in raw_entries.split("|") if item.strip()]
            if not name or not entries:
                raise CommandError(".deck new/set expects name=entry|entry")
            session.configure_deck(name, entries)
            return CommandResponse("deck", args, name, f"牌堆已创建：{name}")
        raise CommandError(f"unknown .deck operation: {operation}")

    def _handle_ank(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        parts = args.strip().split(maxsplit=1)
        operation = parts[0].casefold() if parts else "show"
        value = parts[1].strip() if len(parts) == 2 else ""
        state = session.data.setdefault("ank", {"title": "", "options": []})
        if operation in {"new", "#"}:
            state["title"] = value
            state["options"] = []
        elif operation in {"add", "+"}:
            state["options"].extend(item.strip() for item in value.split("|") if item.strip())
        elif operation in {"del", "-"}:
            index = int(value) - 1
            if not 0 <= index < len(state["options"]):
                raise CommandError("option index out of range")
            state["options"].pop(index)
        elif operation in {"get", "="}:
            if not state["options"]:
                raise CommandError("no ank options")
            selected = state["options"][self.roller.randint(0, len(state["options"]) - 1)]
            state["options"] = []
            return CommandResponse("ak", args, selected, f"抽中：{selected}")
        elif operation == "clr":
            state["title"], state["options"] = "", []
        elif operation != "show":
            raise CommandError(f"unknown .ak operation: {operation}")
        return CommandResponse("ak", args, dict(state), f"{state['title']}：{state['options']}")

    def _handle_rules(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        body = args.strip()
        if body.casefold().startswith("set"):
            rule = body[3:].strip()
            session.data["rules_default"] = rule or None
            return CommandResponse("rules", args, rule or None, f"默认规则：{rule or 'COC'}")
        if not body:
            raise CommandError(".rules requires a query or set [rule]")
        if ":" in body or "：" in body:
            rule, query = re.split(r"[:：]", body, maxsplit=1)
        else:
            rule, query = session.data.get("rules_default") or "COC", body
        result = {"rule": rule, "query": query.strip(), "found": False}
        return CommandResponse("rules", args, result, f"规则查询（{rule}）：{query.strip()}，核心模块未内置词库")

    def _handle_log(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        parts = args.strip().split(maxsplit=1)
        operation = parts[0].casefold() if parts else "show"
        name = parts[1].strip() if len(parts) == 2 else ""
        if operation == "new":
            session.data["log"] = {"name": name or date.today().isoformat(), "enabled": True, "entries": []}
        elif operation in {"on", "off"}:
            session.data.setdefault("log", {"name": date.today().isoformat(), "entries": []})["enabled"] = operation == "on"
        elif operation == "end":
            session.data.setdefault("log", {})["enabled"] = False
        elif operation != "show":
            raise CommandError(f"unknown .log operation: {operation}")
        result = session.data.get("log", {"enabled": False})
        return CommandResponse("log", args, result, str(result))

    @staticmethod
    def _handle_adapter_boundary(
        context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        return CommandResponse(
            metadata.get("command", "adapter"),
            args,
            {"handled_by": "adapter", "args": args},
            "该指令需要由平台适配器处理",
            {"platform_boundary": True},
        )

    def _ensure_card(self, context: MessageContext) -> CharacterCard:
        card = self.identities.characters.resolve(context)
        if card is not None:
            return card
        name = self.identities.nicknames.resolve(context)
        card = self.identities.characters.create(context.actor, name)
        self.identities.characters.bind(context.actor, context.source, card.card_id)
        return card

    def _unique_card_name(self, context: MessageContext, name: str) -> str:
        existing = {card.name.casefold() for card in self.identities.characters.list(context.actor)}
        if name.casefold() not in existing:
            return name
        index = 2
        while f"{name} {index}".casefold() in existing:
            index += 1
        return f"{name} {index}"

    def _generate_coc_attributes(self, variant: int) -> dict[str, Any]:
        normal = ["力量", "体质", "体型", "敏捷", "外貌", "意志", "幸运"]
        attributes = {name: self.roller.roll("3d6*5").total for name in normal}
        attributes["智力"] = self.roller.roll("(2d6+6)*5").total
        attributes["教育"] = self.roller.roll("(2d6+6)*5").total
        attributes.update(
            {
                "生命": (attributes["体质"] + attributes["体型"]) // 10,
                "理智": attributes["意志"],
                "san": attributes["意志"],
                "魔法": attributes["意志"] // 5,
                "闪避": attributes["敏捷"] // 2,
                "灵感": attributes["智力"],
                "知识": attributes["教育"],
                "__Type": f"COC{variant}",
                "__DefaultDice": "d100",
            }
        )
        return attributes

    @staticmethod
    def _split_repeat(args: str) -> tuple[int, str]:
        match = re.match(r"^\s*(\d+)#(.*)$", args, flags=re.DOTALL)
        if not match:
            return 1, args.strip()
        repeat = int(match.group(1))
        if not 1 <= repeat <= 10:
            raise CommandError("repeat count must be in 1..10")
        return repeat, match.group(2).strip()

    @staticmethod
    def _split_roll_reason(body: str) -> tuple[str, str | None]:
        parts = body.split(maxsplit=1)
        if not parts:
            return "", None
        return parts[0], parts[1].strip() if len(parts) == 2 else None

    @staticmethod
    def _split_check_args(body: str) -> tuple[str, str | None, str | None]:
        parts = body.split(maxsplit=1)
        skill = parts[0]
        remaining = parts[1].strip() if len(parts) == 2 else ""
        target: str | None = None
        reason: str | None = None
        if remaining:
            first, *rest = remaining.split(maxsplit=1)
            if re.fullmatch(r"[0-9dDfFkKbBpPxXaA+\-*/().]+", first):
                target = first
                reason = rest[0] if rest else None
            else:
                reason = remaining
        if target is None:
            if skill.isdigit():
                skill, target = "", skill
            else:
                match = re.match(r"^(.+?)(\d+)$", skill)
                if match and not re.search(r"[*+\-/xX]", match.group(1)):
                    skill, target = match.group(1), match.group(2)
        return skill, target, reason

    @staticmethod
    def _read_difficulty(body: str) -> tuple[float, str]:
        if body.startswith("极难"):
            return 0.2, body[2:].strip()
        if body.startswith("困难"):
            return 0.5, body[2:].strip()
        return 1.0, body

    def _evaluate_attribute_expression(self, expression: str | None, attributes: dict[str, Any]) -> int:
        if not expression:
            raise CommandError("attribute expression must not be empty")
        replaced = expression
        for name in sorted(attributes, key=len, reverse=True):
            value = attributes[name]
            if not isinstance(value, (int, float)):
                if isinstance(value, str) and self._can_normalize(value):
                    replacement = f"({value})"
                else:
                    continue
            else:
                replacement = str(int(value))
            replaced = re.sub(
                rf"(?<![\w]){re.escape(name)}(?![\w])",
                replacement,
                replaced,
                flags=re.IGNORECASE,
            )
        unknown = re.sub(r"[0-9dDfFkKbBpPxXaA+\-*/().\s]", "", replaced)
        if unknown:
            raise IdentityError(f"unknown attribute in expression: {unknown}")
        return self.roller.roll(replaced).total

    @staticmethod
    def _is_attribute_or_expression(value: str, attributes: dict[str, Any]) -> bool:
        if re.fullmatch(r"[0-9dDfFkKbBpPxXaA+\-*/().]+", value):
            return True
        return any(key.casefold() == value.casefold() for key in attributes)

    def _can_normalize(self, expression: str) -> bool:
        try:
            self.roller.normalize(expression)
        except Exception:
            return False
        return True

    @staticmethod
    def _parse_attribute_assignment(token: str) -> tuple[str, str, str]:
        match = re.match(r"^(.+?)(?::|=)(.+)$", token)
        if match:
            return match.group(1).lstrip("&"), "=", match.group(2)
        match = re.match(r"^(.+?)([+-])(.+)$", token)
        if match:
            return match.group(1), match.group(2), match.group(3)
        match = re.match(r"^(.+?)(\d+)$", token)
        if match and not match.group(1).isdigit():
            return match.group(1), "=", match.group(2)
        raise CommandError(f"invalid .st assignment: {token}")

    @staticmethod
    def _attribute_key(attributes: dict[str, Any], name: str) -> str:
        for key in attributes:
            if key.casefold() == name.casefold():
                return key
        return name

    @classmethod
    def _find_attribute(cls, attributes: dict[str, Any], name: str) -> Any:
        key = cls._attribute_key(attributes, name)
        if key not in attributes:
            raise IdentityError(f"attribute {name!r} does not exist")
        return attributes[key]

    @classmethod
    def _read_first_numeric(cls, attributes: dict[str, Any], names: tuple[str, ...]) -> int | None:
        for name in names:
            key = cls._attribute_key(attributes, name)
            if key in attributes and isinstance(attributes[key], (int, float)):
                return int(attributes[key])
        return None

    @staticmethod
    def _render_attributes(attributes: dict[str, Any]) -> str:
        if not attributes:
            return "无属性"
        return " ".join(f"{name}:{value}" for name, value in attributes.items())

    @staticmethod
    def _render_card(card: CharacterCard, detailed: bool) -> str:
        if detailed:
            return f"[{card.card_id}] {card.name}<{card.system}>\n{CommandRouter._render_attributes(card.attributes)}"
        visible = {key: value for key, value in card.attributes.items() if not key.startswith("__")}
        return f"[{card.card_id}] {card.name}<{card.system}> {CommandRouter._render_attributes(visible)}"

    @staticmethod
    def _render_roll(response: RollResponse, metadata: dict[str, Any]) -> str:
        prefix = response.display_name
        return f"{prefix}: {response.result.render()}"

    @staticmethod
    def _render_check(check: CheckResult, hidden: bool) -> str:
        result = "隐藏" if hidden else str(check.roll.total)
        return f"{result}/{check.target} {check.success_level}"
