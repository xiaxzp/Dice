from __future__ import annotations

import json
import math
import re
from difflib import get_close_matches
from datetime import date
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from .engine import DiceEngine
from .errors import CommandError, IdentityError, UnknownCommandError
from .insanity import FEARS, LONG_INSANITY, MANIAS, TEMPORARY_INSANITY
from .models import (
    CheckResult,
    DiceTermResult,
    MessageContext,
    PoolResult,
    RollRequest,
    RollResponse,
    RollResult,
)
from .messages import MessageCatalog
from .profiles import CharacterCard, IdentityServices
from .roller import DiceRoller, coc_success_level
from .session import DiceSession
from .special import Deck, DeckEntry, Roulette


_PUBLIC_DECKS = {
    "数字": tuple(str(value) for value in range(10)),
    "大写字母": tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    "小写字母": tuple("abcdefghijklmnopqrstuvwxyz"),
    "天干": tuple("甲乙丙丁戊己庚辛壬癸"),
    "地支": tuple("子丑寅卯辰巳午未申酉戌亥"),
    "硬币": ("正", "反"),
    "性别": ("男", "女"),
    "扑克牌": tuple(
        f"{suit}{rank}"
        for suit in ("红桃", "黑桃", "方片", "梅花")
        for rank in ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
    ) + ("小王", "大王"),
    "麻将牌": tuple(
        [tile for tile in (
            [f"{number}万" for number in "一二三四五六七八九"]
            + [f"{number}筒" for number in "一二三四五六七八九"]
            + [f"{number}条" for number in "一二三四五六七八九"]
            + ["东风", "南风", "西风", "北风", "中", "发", "白"]
        ) for _ in range(4)]
    ),
}

_SKILL_ALIASES = {
    "str": "力量", "dex": "敏捷", "pow": "意志", "siz": "体型", "app": "外貌",
    "luck": "幸运", "luk": "幸运", "con": "体质", "int": "智力", "idea": "灵感",
    "edu": "教育", "san": "理智", "hp": "生命", "mp": "魔法", "侦察": "侦查",
    "计算机": "计算机使用", "cr": "信用评级", "信誉": "信用评级", "驾驶": "汽车驾驶",
    "快速交谈": "话术", "绞具": "绞索", "链枷": "连枷", "步枪": "步枪/霰弹枪",
}

_DEFAULT_SKILLS = {
    "会计": 5, "人类学": 1, "估价": 5, "考古学": 1, "作画": 5, "摄影": 5,
    "表演": 5, "伪造": 5, "文学": 5, "厨艺": 5, "裁缝": 5, "建筑": 5,
    "舞蹈": 5, "捕鱼": 5, "歌唱": 5, "杂技": 5, "取悦": 15, "魅惑": 15,
    "攀爬": 20, "计算机使用": 5, "克苏鲁神话": 0, "乔装": 5, "汽车驾驶": 20,
    "电气维修": 10, "电子学": 1, "话术": 5, "鞭子": 5, "斧": 15, "链锯": 10,
    "连枷": 10, "绞索": 15, "矛": 20, "剑": 20, "手枪": 20, "步枪/霰弹枪": 25,
    "冲锋枪": 15, "弓术": 15, "急救": 30, "历史": 5, "恐吓": 15, "跳跃": 20,
    "法律": 5, "图书馆使用": 20, "聆听": 20, "锁匠": 1, "机械维修": 10,
    "医学": 1, "博物学": 10, "导航": 10, "神秘学": 5, "说服": 10, "精神分析": 1,
    "心理学": 10, "骑术": 5, "侦查": 25, "潜行": 20, "游泳": 20, "投掷": 20,
    "追踪": 10, "闪避": 0, "斗殴": 25,
}


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
        self.messages = MessageCatalog(
            self.identities.repository.store.root,
            random_int=self.roller.randint,
        )
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
            "str": self._handle_message_text,
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
            "rule": self._handle_rules,
            "log": self._handle_log,
            "game": self._handle_game,
            "help": self._handle_help,
        }
        for name in (
            "bot", "reply", "dismiss", "authorize", "send", "group", "link",
            "admin", "cloud", "mod", "user", "system",
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
        pool_match = re.match(r"^(ww|w)(h)?(?=\d+#)(.*)$", lower, flags=re.DOTALL)
        if pool_match:
            command = pool_match.group(1)
            prefix_length = len(command) + bool(pool_match.group(2))
            return _ParsedCommand(
                command,
                body[prefix_length:].strip(),
                {"detailed": command == "ww", "hidden": bool(pool_match.group(2))},
            )
        if lower.startswith("wwh ") or lower.startswith("wh "):
            command = "ww" if lower.startswith("wwh ") else "w"
            prefix_length = 3 if command == "ww" else 2
            return _ParsedCommand(
                command,
                body[prefix_length:].strip(),
                {"detailed": command == "ww", "hidden": True},
            )
        for command in ("authorize", "dismiss", "reply", "welcome", "rules", "rule", "group", "game", "jrrp", "init", "name", "send", "deck", "draw", "dnd", "pc", "ob", "set", "nnn", "nn", "log", "bot", "me", "ti", "li", "en", "ww", "w", "ak"):
            if lower == command or lower.startswith(command + " "):
                return _ParsedCommand(command, body[len(command):].strip(), {"detailed": command == "ww"})
        for command in ("rdc", "rdx", "rsr", "rnc", "rfc", "rbh", "rws"):
            if lower.startswith(command):
                return _ParsedCommand(command, body[len(command):].strip(), {})
        if lower == "str" or lower.startswith("str "):
            return _ParsedCommand("str", body[3:].strip(), {})
        if lower.startswith("st"):
            return _ParsedCommand("st", body[2:].strip(), {})
        if lower.startswith("sc"):
            return _ParsedCommand("sc", body[2:].strip(), {})
        if lower.startswith("ri"):
            return _ParsedCommand("ri", body[2:].strip(), {})
        if lower.startswith("rcb"):
            tail = body[3:]
            count_match = re.match(r"^(\d+)(.*)$", tail)
            if count_match:
                count = count_match.group(1)
                arguments = count_match.group(2).strip()
                return _ParsedCommand("rc", f"b{count} {arguments}".strip(), {"mode": "bonus"})
            return _ParsedCommand("rc", tail.strip(), {"mode": "bonus"})
        if lower.startswith("rcp"):
            tail = body[3:]
            count_match = re.match(r"^(\d+)(.*)$", tail)
            if count_match:
                count = count_match.group(1)
                arguments = count_match.group(2).strip()
                return _ParsedCommand("rc", f"p{count} {arguments}".strip(), {"mode": "penalty"})
            return _ParsedCommand("rc", tail.strip(), {"mode": "penalty"})
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
        if lower == "rd" or lower.startswith("rd "):
            return _ParsedCommand("r", body[2:].strip(), {})
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
            self._roll_response(context, expression, reason)
            for _ in range(repeat)
        ]
        if card is not None:
            for response in responses:
                self._record_roll_stat(
                    context, card, response.result.total, response.result.normalized_expression
                )
        result: RollResponse | list[RollResponse] = responses[0] if repeat == 1 else responses
        if repeat > 1:
            values = self._message_values(context, {**metadata, "reason": reason or ""})
            if metadata.get("short"):
                result_text = "{ " + ",".join(str(response.result.total) for response in responses) + " }"
            else:
                result_text = ", ".join(
                    response.result.render_c_value(detailed=True)
                    for response in responses
                )
            values.update(
                {
                    "turn": repeat,
                    "dice_exp": responses[0].result.render_c().split("=", 1)[0],
                    "res": result_text,
                }
            )
            key = "strRollMultiDiceReason" if reason else "strRollMultiDice"
            rendered = self.messages.render(key, values)
        else:
            rendered = (
                self.messages.render(
                    "strRollHidden",
                    self._message_values(context, {"pc": responses[0].card_name or responses[0].display_name}),
                )
                if metadata.get("hidden")
                else self._render_roll(context, responses[0], metadata)
            )
        response_metadata = dict(metadata)
        response_metadata.update({"repeat": repeat, "reason": reason})
        if metadata.get("hidden"):
            if repeat > 1:
                private_values = self._message_values(
                    context,
                    {
                        "turn": repeat,
                        "dice_exp": responses[0].result.render_c().split("=", 1)[0],
                        "res": ", ".join(
                            response.result.render_c_value(detailed=True)
                            for response in responses
                        ),
                        "reason": reason or "",
                    },
                )
                private_key = "strRollMultiDiceReason" if reason else "strRollMultiDice"
                response_metadata["private_rendered"] = self.messages.render(private_key, private_values)
                response_metadata["public_rendered"] = self.messages.render(
                    "strRollHidden",
                    self._message_values(context, {"pc": responses[0].card_name or responses[0].display_name}),
                )
                rendered = response_metadata["public_rendered"]
            else:
                response_metadata["private_rendered"] = self._render_roll(context, responses[0], metadata)
        return CommandResponse("r", args, result, rendered, response_metadata)

    def _roll_response(
        self,
        context: MessageContext,
        expression: str,
        reason: str | None,
    ) -> RollResponse:
        result = self._roll_session_die(context, expression)
        if result is None:
            return self.engine.roll(RollRequest(context, expression, reason))
        card = self.identities.characters.resolve(context)
        return RollResponse(
            request=RollRequest(context, expression, reason),
            display_name=self.identities.nicknames.resolve(context),
            card_id=card.card_id if card else None,
            card_name=card.name if card else None,
            result=result,
        )

    def _roll_session_die(
        self,
        context: MessageContext,
        expression: str,
    ) -> RollResult | None:
        match = re.fullmatch(r"(?:1)?d(\d+)", expression.strip(), re.IGNORECASE)
        if match is None:
            return None
        sides = int(match.group(1))
        session = self._session_for(context)
        if sides not in session.roulettes:
            return None
        value = session.roll(sides)
        session.data.setdefault("roulette_history", []).append(
            {"sides": sides, "value": value}
        )
        normalized = self.roller.normalize(expression)
        term = DiceTermResult(
            notation=normalized,
            kind="normal",
            subtotal=value,
            rolls=(value,),
            kept=(value,),
            count=1,
            sides=sides,
        )
        return RollResult(
            expression=expression,
            normalized_expression=normalized,
            total=value,
            terms=(term,),
        )

    def _coc_check(
        self,
        context: MessageContext,
        target: int,
        *,
        bonus_dice: int,
        penalty_dice: int,
        rule: int,
    ) -> CheckResult:
        if bonus_dice or penalty_dice:
            return self.roller.coc_check(
                target,
                bonus_dice=bonus_dice,
                penalty_dice=penalty_dice,
                rule=rule,
            )
        roll = self._roll_session_die(context, "d100")
        if roll is None:
            return self.roller.coc_check(target, rule=rule)
        return CheckResult(
            target=target,
            roll=roll,
            success_level=coc_success_level(roll.total, target, rule),
            rule=rule,
        )

    def _record_roll_stat(
        self,
        context: MessageContext,
        card: CharacterCard,
        value: int,
        expression: str,
    ) -> None:
        match = re.fullmatch(r"(?:1)?d(\d+)", expression.strip(), re.IGNORECASE)
        if match is None:
            return
        sides = int(match.group(1))
        if sides > 100:
            return
        current = self.identities.characters.get(context.actor, card.card_id)
        attributes = dict(current.attributes)
        prefix = f"__StatD{sides}"
        attributes[f"{prefix}Cnt"] = int(attributes.get(f"{prefix}Cnt", 0)) + 1
        attributes[f"{prefix}Sum"] = int(attributes.get(f"{prefix}Sum", 0)) + value
        attributes[f"{prefix}SqrSum"] = int(attributes.get(f"{prefix}SqrSum", 0)) + value * value
        self.identities.characters.update(context.actor, current.card_id, attributes=attributes)

    def _record_check_stat(
        self,
        context: MessageContext,
        card: CharacterCard,
        value: int,
        target: int,
    ) -> None:
        current = self.identities.characters.get(context.actor, card.card_id)
        attributes = dict(current.attributes)
        attributes["__StatD100Cnt"] = int(attributes.get("__StatD100Cnt", 0)) + 1
        attributes["__StatD100Sum"] = int(attributes.get("__StatD100Sum", 0)) + value
        attributes["__StatD100SqrSum"] = int(attributes.get("__StatD100SqrSum", 0)) + value * value
        attributes["__StatRcCnt"] = int(attributes.get("__StatRcCnt", 0)) + 1
        attributes["__StatRcSumSuc"] = int(attributes.get("__StatRcSumSuc", 0)) + int(value <= target)
        attributes["__StatRcSumRate"] = int(attributes.get("__StatRcSumRate", 0)) + target
        for key, condition in (
            ("__StatRcCnt1", value == 1),
            ("__StatRcCnt5", value <= 5),
            ("__StatRcCnt96", value >= 96),
            ("__StatRcCnt100", value == 100),
        ):
            if condition:
                attributes[key] = int(attributes.get(key, 0)) + 1
        self.identities.characters.update(context.actor, current.card_id, attributes=attributes)

    def _handle_check(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        repeat, body = self._split_repeat(args)
        if not body:
            raise CommandError(".rc requires a skill or target")
        hidden = metadata.get("hidden", False) or body.startswith("_")
        if hidden:
            body = body[1:].lstrip()
        special_match = re.match(r"^([bp])(\d*)(?:\s+|$)", body, flags=re.IGNORECASE)
        if special_match:
            metadata = dict(metadata)
            special_mode = "bonus" if special_match.group(1).casefold() == "b" else "penalty"
            special_count = int(special_match.group(2) or "1")
            metadata["mode"] = special_mode
            metadata["bonus_dice"] = special_count if special_mode == "bonus" else 0
            metadata["penalty_dice"] = special_count if special_mode == "penalty" else 0
            body = body[special_match.end():].lstrip()
        auto_success = body.startswith("自动成功")
        if auto_success:
            body = body[4:].lstrip()
        difficulty, body = self._read_difficulty(body)
        skill_expression, explicit_target, reason = self._split_check_args(body)
        card = self.identities.characters.resolve(context)
        attributes = dict(card.attributes) if card else {}
        target_expression = explicit_target or skill_expression
        if explicit_target is None:
            canonical = _SKILL_ALIASES.get(skill_expression.casefold(), skill_expression)
            if card is not None and canonical in card.attributes:
                target_expression = canonical
            elif canonical in _DEFAULT_SKILLS:
                attributes[canonical] = _DEFAULT_SKILLS[canonical]
                target_expression = canonical
        target = self._evaluate_attribute_expression(target_expression, attributes)
        target = max(1, int(target * difficulty))
        mode = metadata.get("mode", "normal")
        bonus_dice = int(metadata.get("bonus_dice", 1 if mode == "bonus" else 0))
        penalty_dice = int(metadata.get("penalty_dice", 1 if mode == "penalty" else 0))
        rule = int(self._session_for(context).data.get("coc_rule", 0))
        checks = [
            self._coc_check(
                context,
                target,
                bonus_dice=bonus_dice,
                penalty_dice=penalty_dice,
                rule=rule,
            )
            for _ in range(repeat)
        ]
        if card is not None:
            for check in checks:
                self._record_check_stat(context, card, check.roll.total, target)
        if auto_success:
            checks = [
                check
                if check.success or check.success_level == "fumble"
                else replace(check, success_level="regular_success")
                for check in checks
            ]
        result: CheckResult | list[CheckResult] = checks[0] if repeat == 1 else checks
        render_metadata = dict(metadata)
        render_metadata["repeat"] = repeat
        rendered = self._render_checks(context, checks, skill_expression, reason, hidden, render_metadata)
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
                "bonus_dice": bonus_dice,
                "penalty_dice": penalty_dice,
            }
        )
        if hidden:
            response_metadata["private_rendered"] = self._render_checks(
                context, checks, skill_expression, reason, False, render_metadata
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
        compact = compact.lstrip("s")
        detailed = "d" in compact
        compact = compact.replace("d", "")
        count = int(compact) if compact else 1
        if not 1 <= count <= 10:
            raise CommandError(".coc generation count must be in 1..10")

        display_name = self.identities.nicknames.resolve(context)
        generated: list[dict[str, Any]] = []
        rendered_items: list[str] = []
        for _ in range(count):
            attributes = self._generate_coc_attributes(variant)
            generated.append(attributes)
            rendered_items.append(self._render_coc_attributes(attributes, variant, detailed, count))
        result: dict[str, Any] | list[dict[str, Any]] = generated[0] if count == 1 else generated
        rendered_body = "".join(f"\n{item}" for item in rendered_items)
        rendered = self.messages.render(
            "strCOCBuild",
            self._message_values(
                context,
                {
                    "pc": display_name,
                    "res": rendered_body,
                },
            ),
        )
        response_metadata = dict(metadata)
        response_metadata.update(
            {
                "variant": variant,
                "detailed": detailed,
                "count": count,
                "display_name": display_name,
                "persistent": False,
            }
        )
        return CommandResponse("coc", args, result, rendered, response_metadata)

    def _handle_status(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        body = args.strip()
        card = self.identities.characters.resolve(context)
        if not body:
            help_response = self._handle_help(context, "st", {"command": "help"})
            return CommandResponse("st", args, {}, help_response.rendered)
        if body.casefold() == "show" or body.casefold().startswith("show "):
            if card is None:
                raise CommandError(
                    self.messages.render("strPcNotExistErr", self._message_values(context))
                )
            requested = body[4:].strip()
            if requested:
                key = self._attribute_key(card.attributes, requested)
                if key not in card.attributes:
                    raise CommandError(
                        self.messages.render(
                            "strPropNotFound",
                            self._message_values(context, {"attr": requested}),
                        )
                    )
                result = {requested: card.attributes[key]}
                rendered = self.messages.render(
                    "strProp",
                    self._message_values(context, {"attr": requested, "val": next(iter(result.values()))}),
                )
            else:
                result = self._visible_attributes(card.attributes)
                rendered = self.messages.render(
                    "strPropList",
                    self._message_values(
                        context,
                        {"char": card.name, "show": self._render_card_attributes(card)},
                    ),
                )
            return CommandResponse("st", args, result, rendered)

        if body.casefold() == "clr":
            if card is None:
                raise CommandError(
                    self.messages.render("strPcNotExistErr", self._message_values(context))
                )
            updated = self.identities.characters.update(context.actor, card.card_id, attributes={})
            return CommandResponse(
                "st",
                args,
                updated,
                self.messages.render(
                    "strPropCleared",
                    self._message_values(context, {"char": card.name}),
                ),
            )
        if body.casefold().startswith("del "):
            if card is None:
                raise CommandError(
                    self.messages.render("strPcNotExistErr", self._message_values(context))
                )
            names = body[4:].split()
            attributes = dict(card.attributes)
            for name in names:
                key = self._attribute_key(attributes, name)
                if key not in attributes:
                    raise CommandError(
                        self.messages.render(
                            "strPropNotFound",
                            self._message_values(context, {"attr": name}),
                        )
                    )
                attributes.pop(key)
            updated = self.identities.characters.update(
                context.actor, card.card_id, attributes=attributes
            )
            return CommandResponse(
                "st",
                args,
                updated,
                self.messages.render(
                    "strPropDeleted",
                    self._message_values(context, {"attr": "、".join(names)}),
                ),
            )
        card = card or self._ensure_card(context)
        attributes = dict(card.attributes)
        changed: dict[str, Any] = {}
        for token in self._split_status_assignments(body):
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
        return CommandResponse(
            "st",
            args,
            updated,
            self.messages.render(
                "strSetPropSuccess",
                self._message_values(context, {"pc": card.name, "cnt": len(changed)}),
            ),
        )

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
        roll = self._roll_session_die(context, "d100") or self.roller.roll("d100")
        rule = int(self._session_for(context).data.get("coc_rule", 0))
        success_level = coc_success_level(roll.total, current, rule)
        success = success_level not in {"failure", "fumble"}
        loss_expression = success_loss if success else failure_loss
        if success_level == "fumble":
            loss = self.roller.maximum(loss_expression)
            change_text = f"Max{{{self.roller.normalize(loss_expression).upper()}}}={loss}"
        else:
            loss_result = self.roller.roll(loss_expression)
            loss = loss_result.total
            change_text = loss_result.render_c()
        remaining = max(0, current - loss)
        attributes = dict(card.attributes)
        san_key = self._attribute_key(attributes, "san")
        if san_key == "san" and "理智" in attributes:
            san_key = "理智"
        attributes[san_key] = remaining
        updated = self.identities.characters.update(
            context.actor, card.card_id, attributes=attributes
        )
        self._record_check_stat(context, updated, roll.total, int(current))
        result = {
            "roll": roll,
            "current": current,
            "success": success,
            "loss": loss,
            "remaining": remaining,
            "card": updated,
        }
        rank = self._success_rank(success_level)
        card_name = self.identities.nicknames.resolve(context)
        rendered = self.messages.render(
            "strSanityRoll",
            self._message_values(
                context,
                {
                    "pc": card.name,
                    "res": f"1D100={roll.total}/{current}",
                    "rank": rank,
                    "loss": loss,
                    "change": change_text,
                    "final": remaining,
                    "current": current,
                    "nick": card_name,
                },
            ),
        )
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
        roll_renderings: list[str] = []
        for index in range(repeat):
            if explicit_value is not None:
                value = explicit_value + offset
                roll_renderings.append(str(value))
            else:
                roll_expression = expression if offset == 0 else f"{expression}{offset:+d}"
                roll = self.roller.roll(roll_expression)
                value = roll.total
                roll_renderings.append(roll.render_c())
            entries.append(
                {
                    "name": name if repeat == 1 else f"{name}{index + 1}",
                    "value": value,
                }
            )
        session = self._session_for(context)
        session.data["initiative"] = list(session.data.get("initiative", [])) + entries
        entries.sort(key=lambda item: item["value"], reverse=True)
        result_text = roll_renderings[0]
        if repeat > 1:
            result_text = "\n" + "\n".join(
                f"{index}. {rendering}"
                for index, rendering in enumerate(roll_renderings, start=1)
            )
        rendered = self.messages.render(
            "strRollInit",
            self._message_values(
                context,
                {"char": name, "res": result_text},
            ),
        )
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
            "set": "默认骰面数：.set [1..9999]",
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
            "rule": "规则查询和默认规则：.rule set [规则] 或 .rule s 词条",
            "game": "跑团会话：.game master/join/state/set/close/over/exit",
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
        operation = args.strip().casefold()
        if not operation:
            help_response = self._handle_help(context, "ob", {"command": "help"})
            return CommandResponse("ob", args, {}, help_response.rendered)
        if operation == "join":
            changed = session.add_observer(context.actor)
            result = {"joined": changed, "observers": [item.to_dict() for item in session.observers]}
            rendered = self.messages.render("strObEnter", self._message_values(context)) if changed else self.messages.render("strObEnterAlready", self._message_values(context))
        elif operation == "exit":
            changed = context.actor in session.observers
            session.observers.discard(context.actor)
            result = {"exited": changed, "observers": [item.to_dict() for item in session.observers]}
            rendered = self.messages.render("strObExit", self._message_values(context)) if changed else self.messages.render("strObExitAlready", self._message_values(context))
        elif operation == "list":
            if not session.data.get("game_active", False):
                raise CommandError(
                    self.messages.render("strGameVoidHere", self._message_values(context))
                )
            result = [item.to_dict() for item in sorted(session.observers, key=lambda item: item.key)]
            if result:
                rendered = self.messages.render(
                    "strObList", self._message_values(context)
                ) + "\n" + "\n".join(item["user_id"] for item in result)
            else:
                rendered = self.messages.render("strObListEmpty", self._message_values(context))
        elif operation == "clr":
            if not session.data.get("game_active", False):
                raise CommandError(
                    self.messages.render("strGameVoidHere", self._message_values(context))
                )
            had_observers = bool(session.observers)
            session.observers.clear()
            result = []
            rendered = self.messages.render(
                "strObListClr" if had_observers else "strObListEmpty",
                self._message_values(context),
            )
        elif operation in {"on", "off"}:
            if not session.data.get("game_active", False):
                raise CommandError(
                    self.messages.render("strGameVoidHere", self._message_values(context))
                )
            enabled = session.data.get("observer_enabled", True)
            changed = enabled != (operation == "on")
            session.data["observer_enabled"] = operation == "on"
            result = {"enabled": session.data["observer_enabled"], "changed": changed}
            rendered = self.messages.render(
                (
                    "strObOn" if operation == "on" and changed else
                    "strObOnAlready" if operation == "on" else
                    "strObOff" if changed else "strObOffAlready"
                ),
                self._message_values(context),
            )
        else:
            raise CommandError(".ob expects join, exit, list, clr, on, or off")
        return CommandResponse("ob", args, result, rendered, {"operation": operation})

    def _handle_game(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        parts = args.strip().split(maxsplit=1)
        if not parts:
            help_response = self._handle_help(context, "game", {"command": "help"})
            return CommandResponse("game", args, {}, help_response.rendered)
        operation = parts[0].casefold()
        value = parts[1].strip() if len(parts) == 2 else ""
        if operation == "new":
            session.sources.clear()
            session.game_masters.clear()
            session.players.clear()
            session.observers.clear()
            session.roulettes.clear()
            session.decks.clear()
            session.data.clear()
            session.data["name"] = value or session.session_id
            session.data["game_id"] = session.data["name"]
            session.data["game_active"] = True
            session.add_source(context.source)
            session.add_gm(context.actor)
            return CommandResponse(
                "game",
                args,
                {"session_id": session.session_id, "created": True},
                self.messages.render(
                    "strGameNew",
                    self._message_values(context, {"game_id": session.data["game_id"]}),
                ),
            )
        if operation == "master":
            changed = session.add_gm(context.actor)
            if changed:
                rendered = self.messages.render("strGameMastered", self._message_values(context))
                result: Any = {"changed": True}
            else:
                masters = sorted(session.game_masters, key=lambda item: item.key)
                result = {"changed": False, "masters": [item.to_dict() for item in masters]}
                rendered = self.messages.render(
                    "strGameMasterList",
                    self._message_values(
                        context,
                        {"items": "\n".join(item.user_id for item in masters)},
                    ),
                )
            return CommandResponse("game", args, result, rendered)
        if operation == "join":
            changed = session.add_player(context.actor)
            rendered = self.messages.render(
                "strGameJoined" if changed else "strGamePlayerAlready",
                self._message_values(context),
            )
            return CommandResponse("game", args, {"changed": changed}, rendered)
        if operation == "exit":
            changed = session.remove_player(context.actor) or session.remove_gm(context.actor)
            rendered = self.messages.render(
                "strGameExited" if changed else "strGameNotJoined",
                self._message_values(context),
            )
            return CommandResponse("game", args, {"changed": changed}, rendered)
        if operation in {"close", "over"}:
            game_id = str(session.data.get("game_id", session.data.get("name", session.session_id)))
            session.data["closed"] = True
            session.data["game_active"] = False
            rendered = self.messages.render(
                "strGameAreaClosed" if operation == "close" else "strGameOver",
                self._message_values(context, {"game_id": game_id}),
            )
            return CommandResponse("game", args, {"closed": True}, rendered)
        if operation == "open":
            session.data["closed"] = False
            session.data["game_active"] = True
            if value:
                session.data["game_id"] = value
            game_id = str(session.data.get("game_id", session.data.get("name", session.session_id)))
            return CommandResponse(
                "game",
                args,
                {"closed": False},
                self.messages.render(
                    "strGameAreaOpen",
                    self._message_values(context, {"game_id": game_id}),
                ),
            )
        if operation == "set":
            if "=" not in value:
                raise CommandError(".game set expects key=value")
            key, item = (part.strip() for part in value.split("=", 1))
            try:
                parsed: Any = json.loads(item)
            except json.JSONDecodeError:
                parsed = item
            session.data[key] = parsed
            return CommandResponse(
                "game",
                args,
                {key: parsed},
                self.messages.render(
                    "strGameItemSet",
                    self._message_values(context, {"set_item": key, "set_val": parsed}),
                ),
            )
        if operation == "call":
            players = sorted(session.players, key=lambda item: item.key)
            result = [actor.to_dict() for actor in players]
            rendered = self.messages.render(
                "strGamePlayerCall" if players else "strGamePlayerEmpty",
                self._message_values(context, {"items": "\n".join(actor.user_id for actor in players)}),
            )
            return CommandResponse("game", args, result, rendered)
        if operation == "state":
            result = session.to_dict()
            return CommandResponse("game", args, result, self._render_game_state(context, session))
        if operation == "rou":
            if not session.data.get("game_active", False):
                raise CommandError(
                    self.messages.render("strGameVoidHere", self._message_values(context))
                )
            rou_parts = value.split()
            action = rou_parts[0].casefold() if rou_parts else "show"
            if action in {"clr", "reset"}:
                if action == "clr":
                    session.roulettes.clear()
                    session.data.pop("roulette_history", None)
                    return CommandResponse(
                        "game", args, {}, self.messages.render("strGameRouletteClear", self._message_values(context))
                    )
                for roulette in session.roulettes.values():
                    roulette.reset()
                session.data["roulette_history"] = []
                return CommandResponse(
                    "game", args, session.to_dict()["roulettes"],
                    self.messages.render("strGameRouletteReset", self._message_values(context)),
                )
            if action == "hist":
                history = list(session.data.get("roulette_history", []))
                grouped: dict[int, list[int]] = {}
                for item in history:
                    if isinstance(item, dict):
                        sides = int(item["sides"])
                        value = int(item["value"])
                    else:
                        sides = next(
                            (sides for sides in session.roulettes if int(item) <= sides),
                            0,
                        )
                        value = int(item)
                    if sides:
                        grouped.setdefault(sides, []).append(value)
                rendered = self.messages.render(
                    "strGameRouletteHistory" if history else "strGameRouletteEmpty",
                    self._message_values(
                        context,
                        {
                            "hist": "\n".join(
                                f"D{sides}=" + " ".join(map(str, values))
                                for sides, values in sorted(grouped.items())
                            )
                        },
                    ),
                )
                return CommandResponse("game", args, history, rendered)
            match = re.fullmatch(r"(\d+)(?:\*(\d+))?", action)
            if match:
                sides = int(match.group(1))
                copies = int(match.group(2) or "1")
                if sides <= 0 or copies <= 0 or sides * copies > 100:
                    raise CommandError(".game rou requires positive sides/copies with total at most 100")
                roulette = session.configure_roulette(sides, copies)
                session.data["roulette_history"] = []
                return CommandResponse(
                    "game", args, roulette.to_dict(),
                    self.messages.render(
                        "strGameRouletteSet",
                        self._message_values(context, {"face": sides}),
                    ),
                )
            if action == "show":
                result = {str(sides): roulette.to_dict() for sides, roulette in session.roulettes.items()}
                rendered = self.messages.render(
                    "strGameRouletteHistory" if result else "strGameRouletteEmpty",
                    self._message_values(context, {"hist": self._render_roulette_list(result)}),
                )
                return CommandResponse("game", args, result, rendered)
            raise CommandError(".game rou expects sides[*copies], hist, clr, reset, or show")
        raise CommandError(f"unknown .game operation: {operation}")

    def _handle_set(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        value = args.strip()
        if not value:
            self.identities.settings.remove(context.actor, "default_dice")
            return CommandResponse(
                "set",
                args,
                {"default_sides": 100},
                self.messages.render(
                    "strSetDefaultDice",
                    self._message_values(context, {"default": 100}),
                ),
            )
        try:
            sides = int(value)
        except ValueError as error:
            raise CommandError(
                self.messages.render("strSetTooBig", self._message_values(context))
            ) from error
        if sides == 0:
            raise CommandError(
                self.messages.render("strSetCannotBeZero", self._message_values(context))
            )
        if not 1 <= sides <= 9999:
            raise CommandError(
                self.messages.render("strSetTooBig", self._message_values(context))
            )
        card = self.identities.characters.resolve(context)
        if card is None:
            self.identities.settings.set(context.actor, "default_dice", f"d{sides}")
        else:
            attributes = dict(card.attributes)
            attributes["__DefaultDice"] = f"d{sides}"
            self.identities.characters.update(context.actor, card.card_id, attributes=attributes)
        return CommandResponse(
            "set",
            args,
            {"default_sides": sides},
            self.messages.render(
                "strSetDefaultDice",
                self._message_values(context, {"default": sides}),
            ),
        )

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
        if count > 10:
            raise CommandError(
                self.messages.render(
                    "strNameNumTooBig",
                    self._message_values(context),
                )
            )
        if count == 0:
            raise CommandError(
                self.messages.render(
                    "strNameNumCannotBeZero",
                    self._message_values(context),
                )
            )
        result = self._random_names(kind, count)
        return CommandResponse(
            "name",
            args,
            result,
            self.messages.render(
                "strNameGenerator",
                self._message_values(context, {"res": "、".join(result)}),
            ),
            {"kind": kind, "count": count},
        )

    def _handle_nickname(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        body = args.strip()
        if metadata.get("command") == "nnn":
            body = self._random_names(body.casefold() or "all", 1)[0]
        elif not body:
            help_response = self._handle_help(context, "nn", {"command": "help"})
            return CommandResponse("nn", args, {}, help_response.rendered)
        if body.casefold() == "clr":
            old_nick = self.identities.nicknames.resolve(context)
            result = self.identities.nicknames.clear(context.actor)
            return CommandResponse("nn", args, result, self.messages.render("strNameClr", self._message_values(context, {"old_nick": old_nick})))
        if body.casefold() == "del":
            source = None if context.source.kind == "private" else context.source
            old_nick = self.identities.nicknames.resolve(context)
            result = self.identities.nicknames.remove(context.actor, source)
            return CommandResponse(
                "nn",
                args,
                result,
                self.messages.render(
                    "strNameDel" if result else "strNameDelEmpty",
                    self._message_values(context, {"old_nick": old_nick}),
                ),
            )
        if body.casefold() == "nnn" or body.casefold().startswith("nnn "):
            kind = body[3:].strip().casefold() or "all"
            body = self._random_names(kind, 1)[0]
        elif body.casefold().startswith("n "):
            body = body[2:].strip()
        if len(body.encode("utf-8")) > 50:
            raise CommandError(
                self.messages.render("strNameTooLongErr", self._message_values(context))
            )
        source = None if context.source.kind == "private" else context.source
        old_nick = self.identities.nicknames.resolve(context)
        result = self.identities.nicknames.set(context.actor, body, source)
        return CommandResponse(
            "nn",
            args,
            result,
            self.messages.render(
                "strNameSet",
                self._message_values(context, {"old_nick": old_nick, "new_nick": result}),
            ),
        )

    def _handle_dnd(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        try:
            count = int(args.strip() or "1")
        except ValueError as error:
            raise CommandError(
                self.messages.render("strCharacterInvalid", self._message_values(context))
            ) from error
        if count > 10:
            raise CommandError(
                self.messages.render("strBuildTooMany", self._message_values(context))
            )
        if count == 0:
            raise CommandError(
                self.messages.render("strCharacterCannotBeZero", self._message_values(context))
            )
        display_name = self.identities.nicknames.resolve(context)
        generated: list[dict[str, Any]] = []
        for index in range(count):
            attributes = {name: self.roller.roll("4d6k3").total for name in ("力量", "敏捷", "体质", "智力", "感知", "魅力")}
            generated.append(attributes)
        result: dict[str, Any] | list[dict[str, Any]] = generated[0] if count == 1 else generated
        rendered = self.messages.render(
            "strDNDBuild",
            self._message_values(
                context,
                {"res": "\n" + self._render_dnd_cards(generated)},
            ),
        )
        return CommandResponse("dnd", args, result, rendered, {"count": count})

    def _handle_pc(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        parts = args.split(maxsplit=1)
        if not parts:
            help_response = self._handle_help(context, "pc", {"command": "help"})
            return CommandResponse("pc", args, {}, help_response.rendered)
        operation = parts[0].casefold()
        value = parts[1].strip() if len(parts) == 2 else ""
        current = self.identities.characters.resolve(context)
        if operation == "new":
            name = value or self.identities.nicknames.resolve(context)
            card = self.identities.characters.create(context.actor, self._unique_card_name(context, name), system="COC7")
            return CommandResponse(
                "pc", args, card,
                self.messages.render(
                    "strPcNewEmptyCard",
                    self._message_values(context, {"type": card.system, "char": card.name}),
                ),
            )
        if operation == "list":
            cards = self.identities.characters.list(context.actor)
            listed = [
                f"[{card.card_id}]<{card.system}>{card.name}" for card in cards
            ]
            listed.insert(0, "[0]<COC7>角色卡")
            listed.append("default:角色卡")
            return CommandResponse(
                "pc", args, cards,
                self.messages.render(
                    "strPcCardList",
                    self._message_values(
                        context,
                        {"show": "\n".join(listed)},
                    ),
                ),
            )
        if operation == "grp":
            profile = self.identities.repository.load(context.actor)
            result = dict(profile.bindings)
            cards = profile.cards
            lines = []
            for scope, card_id in result.items():
                card = cards.get(card_id)
                if card is not None:
                    lines.append(
                        f"default:{card.name}" if scope == "global" else f"({scope}){card.name}"
                    )
            return CommandResponse(
                "pc",
                args,
                result,
                self.messages.render(
                    "strPcGroupList",
                    self._message_values(context, {"show": "\n".join(lines)}),
                ),
            )
        if operation == "show":
            card = self._card_by_ref(context, value) if value else current
            result = card.to_dict() if card else {}
            display_card = card or CharacterCard("0", "角色卡", "COC7")
            rendered = (
                self.messages.render(
                    "strPcCardShow",
                    self._message_values(
                        context,
                        {
                            "type": display_card.system,
                            "char": display_card.name,
                            "show": self._render_card_attributes(display_card),
                        },
                    ),
                )
            )
            return CommandResponse("pc", args, result, rendered)
        if operation == "tag":
            if not value:
                source = None if context.source.kind == "private" else context.source
                self.identities.characters.unbind(context.actor, source)
                return CommandResponse(
                    "pc", args, {},
                    self.messages.render("strPcCardReset", self._message_values(context)),
                )
            card = self._card_by_ref(context, value)
            if context.source.kind == "private":
                self.identities.characters.bind_global(context.actor, card.card_id)
            else:
                self.identities.characters.bind(context.actor, context.source, card.card_id)
            return CommandResponse(
                "pc", args, card,
                self.messages.render(
                    "strPcCardSet", self._message_values(context, {"char": card.name})
                ),
            )
        if operation == "clr":
            cards = self.identities.characters.list(context.actor)
            if not cards:
                raise CommandError(
                    self.messages.render("strPcNotExistErr", self._message_values(context))
                )
            for card in cards:
                self.identities.characters.delete(context.actor, card.card_id)
            return CommandResponse(
                "pc", args, len(cards),
                self.messages.render("strPcClr", self._message_values(context)),
            )
        if operation == "stat":
            return self._render_card_statistics(context, args, current)
        if operation == "type":
            if not value:
                result = {"attr": "模板类", "val": current.system if current else "COC7"}
                return CommandResponse(
                    "pc",
                    args,
                    result,
                    self.messages.render(
                        "strProp",
                        self._message_values(context, result),
                    ),
                )
            if current is None:
                raise CommandError("no current character card")
            updated = self.identities.characters.update(
                context.actor, current.card_id, system=value
            )
            return CommandResponse(
                "pc", args, updated,
                self.messages.render(
                    "strPcTempChange",
                    self._message_values(context, {"pc": current.name, "new_type": value}),
                ),
            )
        if operation == "temp":
            if current is None:
                raise CommandError("no current character card")
            result = {"system": current.system, "attributes": dict(current.attributes)}
            return CommandResponse("pc", args, result, self._render_attributes(result["attributes"]))
        if operation == "tojson":
            card = self._card_by_ref(context, value) if value else current
            if card is None:
                raise CommandError(
                    self.messages.render("strPcNotExistErr", self._message_values(context))
                )
            result = card.to_dict()
            rendered_json = json.dumps(result, ensure_ascii=False, sort_keys=True)
            return CommandResponse(
                "pc",
                args,
                result,
                self.messages.render(
                    "strPcCardShow",
                    self._message_values(
                        context,
                        {"type": card.system, "char": card.name, "show": rendered_json},
                    ),
                ),
            )
        if operation == "cpy":
            if "=" in value:
                destination, target = (item.strip() for item in value.split("=", 1))
            else:
                target = value.strip()
                destination = current.name if current is not None else "副本"
            if not target:
                raise CommandError(".pc cpy expects destination=source")
            source = self._card_by_ref(context, target)
            card = self.identities.characters.create(
                context.actor,
                self._unique_card_name(context, destination),
                system=source.system,
                attributes=source.attributes,
            )
            return CommandResponse(
                "pc",
                args,
                card,
                self.messages.render(
                    "strPcCardCpy",
                    self._message_values(
                        context, {"char1": card.name, "char2": source.name}
                    ),
                ),
            )
        if operation in {"build", "redo"} and value:
            current = self._card_by_ref(context, value)
        if current is None:
            raise CommandError("no current character card")
        if operation == "nn":
            card = self.identities.characters.rename(context.actor, current.card_id, value)
            return CommandResponse(
                "pc", args, card,
                self.messages.render(
                    "strPcCardRename",
                    self._message_values(context, {"old_name": current.name, "new_name": card.name}),
                ),
            )
        if operation == "del":
            card = self._card_by_ref(context, value) if value else current
            self.identities.characters.delete(context.actor, card.card_id)
            return CommandResponse(
                "pc", args, {},
                self.messages.render("strPcCardDel", self._message_values(context, {"char": card.name})),
            )
        if operation in {"build", "redo"}:
            attributes = {} if operation == "redo" else dict(current.attributes)
            attributes.update(self._generate_coc_attributes(7))
            card = self.identities.characters.update(context.actor, current.card_id, attributes=attributes)
            key = "strPcCardRedo" if operation == "redo" else "strPcCardBuild"
            return CommandResponse(
                "pc", args, card,
                self.messages.render(
                    key,
                    self._message_values(
                        context,
                        {
                            "char": card.name,
                            "show": self._render_card_attributes(card),
                        },
                    ),
                ),
            )
        raise CommandError(f"unknown .pc operation: {operation}")

    def _render_card_statistics(
        self,
        context: MessageContext,
        args: str,
        card: CharacterCard | None,
    ) -> CommandResponse:
        if card is None:
            return CommandResponse(
                "pc", args, {},
                self.messages.render("strPcStatEmpty", self._message_values(context)),
            )
        face = self._default_sides(card)
        attributes = card.attributes
        dice_key = f"__StatD{face}"
        count = int(attributes.get(f"{dice_key}Cnt", 0))
        checks = int(attributes.get("__StatRcCnt", 0))
        if count <= 0 and checks <= 0:
            return CommandResponse(
                "pc", args, {},
                self.messages.render(
                    "strPcStatEmpty", self._message_values(context, {"pc": card.name})
                ),
            )
        result: dict[str, Any] = {"dice": {}, "checks": {}}
        lines: list[str] = []
        if count > 0 and face <= 100:
            total = int(attributes.get(f"{dice_key}Sum", 0))
            square_total = int(attributes.get(f"{dice_key}SqrSum", 0))
            mean = total / count
            deviation = math.sqrt(max(0.0, square_total / count - mean * mean))
            expected_mean = (face + 1) / 2
            expected_deviation = math.sqrt((face * face - 1) / 12)
            result["dice"] = {
                "sides": face,
                "count": count,
                "mean": mean,
                "expected_mean": expected_mean,
                "stddev": deviation,
                "expected_stddev": expected_deviation,
            }
            lines.extend(
                (
                    f"D{face}统计次数：{count}",
                    f"均值：{mean:.2f} [期望 {expected_mean:.2f}]",
                    f"标准差：{deviation:.2f} [期望 {expected_deviation:.2f}]",
                )
            )
        if checks > 0:
            successes = int(attributes.get("__StatRcSumSuc", 0))
            expected_rate = int(attributes.get("__StatRcSumRate", 0)) / checks
            result["checks"] = {
                "count": checks,
                "successes": successes,
                "success_rate": successes / checks,
                "expected_rate": expected_rate / 100,
                "one": int(attributes.get("__StatRcCnt1", 0)),
                "low": int(attributes.get("__StatRcCnt5", 0)),
                "high": int(attributes.get("__StatRcCnt96", 0)),
                "hundred": int(attributes.get("__StatRcCnt100", 0)),
            }
            lines.append(f"检定成功率：{successes}/{checks}={successes / checks * 100:.2f}% [期望{expected_rate:.2f}%]")
            lines.append(
                f"5- | 96+ 出现数：{result['checks']['low']} | {result['checks']['high']}"
            )
            lines.append(
                f"1 | 100 出现数：{result['checks']['one']} | {result['checks']['hundred']}"
            )
        rendered = self.messages.render(
            "strPcStatShow",
            self._message_values(context, {"pc": card.name, "stat": "\n".join(lines)}),
        )
        return CommandResponse("pc", args, result, rendered)

    @staticmethod
    def _default_sides(card: CharacterCard) -> int:
        expression = str(card.attributes.get("__DefaultDice", "d100"))
        match = re.fullmatch(r"(?:1)?d(\d+)", expression, re.IGNORECASE)
        return int(match.group(1)) if match else 100

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
            return CommandResponse(
                "setcoc",
                args,
                rule,
                self.messages.render(
                    "strDefaultCOCShowDefault" if rule == 0 else "strDefaultCOCShow",
                    self._message_values(context, {"rule": rule}),
                ),
            )
        if value == "clr":
            session.data.pop("coc_rule", None)
            return CommandResponse(
                "setcoc", args, 0,
                self.messages.render("strDefaultCOCClr", self._message_values(context)),
            )
        try:
            rule = int(value)
        except ValueError as error:
            raise CommandError(".setcoc expects 0..6, show, or clr") from error
        if not 0 <= rule <= 6:
            raise CommandError(
                self.messages.render("strDefaultCOCNotFound", self._message_values(context))
            )
        session.data["coc_rule"] = rule
        return CommandResponse(
            "setcoc", args, rule,
            self.messages.render(
                "strDefaultCOCSet", self._message_values(context, {"rule": rule})
            ) + str(rule),
        )

    def _handle_madness(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        temporary = metadata.get("command") == "ti"
        symptom_roll = self.roller.roll("d10").total
        duration_roll = self.roller.roll("d10").total
        details: dict[str, Any] = {}
        if symptom_roll in {9, 10}:
            detail_roll = self.roller.roll("d100").total
            detail_table = FEARS if symptom_roll == 9 else MANIAS
            details = {
                "detail_roll": f"1D100={detail_roll}",
                "detail": detail_table[detail_roll],
            }
        template = (TEMPORARY_INSANITY if temporary else LONG_INSANITY)[symptom_roll]
        symptom = template.format(
            pc=self.identities.characters.resolve(context).name
            if self.identities.characters.resolve(context)
            else self.identities.nicknames.resolve(context),
            nick=self.identities.nicknames.resolve(context),
            dur=f"1D10={duration_roll}",
            detail_roll=details.get("detail_roll", ""),
            detail=details.get("detail", ""),
        )
        symptom = f"1D10={symptom_roll}\n症状: {symptom}"
        result = {
            "type": "temporary" if temporary else "indefinite",
            "roll": symptom_roll,
            "symptom": symptom,
            "duration": duration_roll,
            **details,
        }
        key = "strTempInsane" if temporary else "strLongInsane"
        return CommandResponse(
            "ti" if temporary else "li",
            args,
            result,
            self.messages.render(
                key,
                self._message_values(context, {"res": symptom}),
            ),
        )

    def _handle_growth(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        parts = args.split(maxsplit=2)
        if not parts:
            raise CommandError(".en requires a skill")
        skill = parts[0] if not parts[0].lstrip("+-").isdigit() else ""
        card = self.identities.characters.resolve(context) or self._ensure_card(context)
        skill = _SKILL_ALIASES.get(skill.casefold(), skill)
        value_index = 1 if skill else 0
        current = self._read_first_numeric(card.attributes, (skill,)) if skill else None
        if len(parts) > value_index and not parts[value_index].startswith(("+", "-")):
            current = self._evaluate_attribute_expression(parts[value_index], card.attributes)
        if not skill:
            skill = self.messages.get("strEnDefaultName")
        if current is None:
            current = _DEFAULT_SKILLS.get(skill)
        if current is None:
            raise CommandError(f"unknown skill: {skill}")
        change_expression = parts[value_index] if len(parts) > value_index and parts[value_index].startswith(("+", "-")) else ""
        if len(parts) > value_index + 1:
            change_expression = parts[value_index + 1]
        failure_expression = ""
        success_expression = "1d10"
        if "/" in change_expression:
            failure_expression, success_expression = change_expression.split("/", 1)
        elif change_expression:
            success_expression = change_expression
        roll = self._roll_session_die(context, "d100") or self.roller.roll("d100")
        success = roll.total > current or roll.total >= 96
        change = 0
        if success:
            change = self._evaluate_attribute_expression(success_expression, card.attributes)
        elif failure_expression:
            change = self._evaluate_attribute_expression(failure_expression, card.attributes)
        updated_value = current + change
        attributes = dict(card.attributes)
        key = self._attribute_key(attributes, skill)
        attributes[key] = updated_value
        updated = self.identities.characters.update(context.actor, card.card_id, attributes=attributes)
        self._record_roll_stat(context, updated, roll.total, "d100")
        result = {"skill": skill, "current": current, "roll": roll, "success": success, "value": updated_value, "card": updated}
        key = "strEnRollSuccess" if success and change else "strEnRollNotChange" if not change else "strEnRollFailure"
        rendered = self.messages.render(
            key,
            self._message_values(
                context,
                {
                    "pc": card.name,
                    "nick": self.identities.nicknames.resolve(context),
                    "attr": skill,
                    "res": f"1D100={roll.total}/{current} " + self.messages.render(
                        "strSuccess" if success else "strFailure",
                        self._message_values(context),
                    ),
                    "change": change,
                    "final": updated_value,
                },
            ),
        )
        return CommandResponse("en", args, result, rendered)

    def _handle_message_text(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        del context, metadata
        parts = args.strip().split(maxsplit=1)
        if not parts:
            result = {key: self.messages.get(key) for key in self.messages.keys()}
            return CommandResponse("str", args, result, "\n".join(f"{key}: {value}" for key, value in result.items()))
        key = parts[0]
        if len(parts) == 1 or parts[1].casefold() == "show":
            value = self.messages.get(key)
            if not value and key not in self.messages.custom and key not in self.messages.keys():
                raise CommandError(f"message key {key!r} does not exist")
            return CommandResponse("str", args, value, value, {"key": key, "operation": "show"})
        value = parts[1]
        if value.casefold() == "reset":
            existed = self.messages.reset(key)
            return CommandResponse("str", args, self.messages.get(key), self.messages.get(key), {"key": key, "operation": "reset", "changed": existed})
        if value.casefold() == "null":
            value = ""
        self.messages.set(key, value)
        return CommandResponse("str", args, value, value, {"key": key, "operation": "set"})

    def _handle_init(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        operation = args.strip()
        if not operation:
            help_response = self._handle_help(context, "ri/init", {"command": "help"})
            return CommandResponse("init", args, {}, help_response.rendered)
        if operation.casefold() == "clr":
            if "initiative" not in session.data:
                return CommandResponse(
                    "init", args, [],
                    self.messages.render(
                        "strGMTableNotExist",
                        self._message_values(context, {"table_name": "先攻"}),
                    ),
                )
            session.data.pop("initiative", None)
            return CommandResponse(
                "init", args, [],
                self.messages.render(
                    "strGMTableClr",
                    self._message_values(context, {"table_name": "先攻"}),
                ),
            )
        if operation.casefold().startswith("del"):
            target = operation[3:].strip()
            if not target:
                raise CommandError(
                    self.messages.render(
                        "strGMTableItemEmpty",
                        self._message_values(context, {"table_name": "先攻"}),
                    )
                )
            if "initiative" not in session.data:
                return CommandResponse(
                    "init", args, [],
                    self.messages.render(
                        "strGMTableNotExist",
                        self._message_values(context, {"table_name": "先攻"}),
                    ),
                )
            entries = list(session.data.get("initiative", []))
            retained = [item for item in entries if item["name"] != target]
            if len(retained) == len(entries):
                raise CommandError(
                    self.messages.render(
                        "strGMTableItemNotFound",
                        self._message_values(
                            context, {"table_name": "先攻", "table_item": target}
                        ),
                    )
                )
            session.data["initiative"] = retained
            return CommandResponse(
                "init", args, target,
                self.messages.render(
                    "strGMTableItemDel",
                    self._message_values(
                        context, {"table_name": "先攻", "table_item": target}
                    ),
                ),
            )
        if operation.casefold() not in {"show", "list"}:
            help_response = self._handle_help(context, "ri/init", {"command": "help"})
            return CommandResponse("init", args, {}, help_response.rendered)
        if "initiative" not in session.data:
            return CommandResponse(
                "init", args, [],
                self.messages.render(
                    "strGMTableNotExist",
                    self._message_values(context, {"table_name": "先攻"}),
                ),
            )
        entries = sorted(
            session.data["initiative"],
            key=lambda item: (item["value"], item["name"]),
            reverse=True,
        )
        result = "".join(
            f"\n{index}.{item['name']}: {item['value']}"
            for index, item in enumerate(entries, start=1)
        )
        return CommandResponse(
            "init", args, entries,
            self.messages.render(
                "strGMTableShow",
                self._message_values(context, {"table_name": "先攻", "res": result}),
            ),
        )

    def _handle_pool(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        repeat, body = self._split_repeat(args)
        expression, reason = self._split_roll_reason(body)
        match = re.fullmatch(r"(\d+)(?:\s*a\s*(\d+)?)?", expression, flags=re.IGNORECASE)
        if match:
            count = int(match.group(1))
            explode_at = int(match.group(2) or 10)
            notation = f"{count}" + (f"a{explode_at}" if "a" in expression.casefold() else "D")
        else:
            card = self.identities.characters.resolve(context)
            if card is None:
                raise CommandError(".w expects [count]a[target] or a card expression")
            count = self._evaluate_attribute_expression(expression, card.attributes)
            explode_at = 10
            notation = f"{count}D"
        if not 5 <= explode_at <= 11:
            raise CommandError("dice pool explosion threshold must be in 5..11")
        card = self.identities.characters.resolve(context)
        session = self._session_for(context)
        target = int(
            session.data.get(
                "__DPTarget",
                card.attributes.get("__DPTarget", 8) if card is not None else 8,
            )
        )
        results = [
            self.roller.pool(count, target=target, explode_at=explode_at)
            for _ in range(repeat)
        ]
        display_name = card.name if card is not None else self.identities.nicknames.resolve(context)
        values = self._message_values(
            context,
            {
                "pc": display_name,
                "reason": reason or "",
                "turn": repeat,
                "dice_exp": notation,
            },
        )
        detailed = bool(metadata.get("detailed"))
        if repeat > 1 and not detailed:
            values["res"] = "{ " + ",".join(str(result.successes) for result in results) + " }"
            rendered = self.messages.render(
                "strRollMultiDiceReason" if reason else "strRollMultiDice",
                values,
            )
        else:
            rendered_items = []
            for result in results:
                values["res"] = result.render_c(notation, detailed=detailed)
                rendered_items.append(
                    self.messages.render(
                        "strRollDiceReason" if reason else "strRollDice",
                        values,
                    )
                )
            rendered = "\n".join(rendered_items)
        response_metadata = {
            **metadata,
            "count": count,
            "target": target,
            "explode_at": explode_at,
            "repeat": repeat,
            "reason": reason,
        }
        if metadata.get("hidden") and context.source.kind != "private":
            response_metadata["private_rendered"] = rendered
            rendered = self.messages.render(
                "strRollHidden", self._message_values(context, {"pc": display_name})
            )
        result_value: PoolResult | list[PoolResult] = results[0] if repeat == 1 else results
        return CommandResponse(
            "ww" if detailed else "w", args, result_value, rendered, response_metadata
        )

    def _handle_action(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        body = args.strip()
        if body.casefold() in {"on", "off"}:
            session = self._session_for(context)
            requested = body.casefold() == "on"
            enabled = session.data.get("me_enabled", True)
            changed = enabled != requested
            session.data["me_enabled"] = requested
            return CommandResponse(
                "me",
                args,
                requested,
                self.messages.render(
                    (
                        "strMeOn" if requested and changed else
                        "strMeOnAlready" if requested else
                        "strMeOff" if changed else "strMeOffAlready"
                    ),
                    self._message_values(context),
                ),
            )
        if not body:
            raise CommandError(self.messages.render("strActionEmpty", self._message_values(context)))
        if self._session_for(context).data.get("me_enabled", True) is False:
            raise CommandError(
                self.messages.render("strMEDisabledErr", self._message_values(context))
            )
        return CommandResponse("me", args, {"actor": context.actor.to_dict(), "action": body}, f"{self.identities.nicknames.resolve(context)}{body}")

    def _handle_jrrp(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        operation = args.strip().casefold()
        if operation in {"on", "off"}:
            requested = operation == "on"
            enabled = session.data.get("jrrp_enabled", True)
            changed = enabled != requested
            session.data["jrrp_enabled"] = requested
            key = (
                "strJrrpOn" if requested and changed else
                "strJrrpOnAlready" if requested else
                "strJrrpOff" if changed else "strJrrpOffAlready"
            )
            return CommandResponse(
                "jrrp", args, requested,
                self.messages.render(key, self._message_values(context)),
                {"enabled": requested, "changed": changed},
            )
        if session.data.get("jrrp_enabled", True) is False:
            raise CommandError("在本群中JRRP功能已被禁用")
        key = f"jrrp:{date.today().isoformat()}:{context.actor.key}"
        values = session.data.setdefault("jrrp_values", {})
        if key not in values:
            values[key] = self.roller.randint(1, 100)
        return CommandResponse(
            "jrrp",
            args,
            values[key],
            self.messages.render(
                "strJrrp",
                self._message_values(context, {"res": values[key]}),
            ),
        )

    def _handle_welcome(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        body = args.strip()
        if not body:
            return self._handle_help(context, "welcome", {"command": "help"})
        if context.source.kind == "private":
            raise CommandError(
                self.messages.render("strWelcomePrivate", self._message_values(context))
            )
        if body.casefold() == "clr":
            existed = session.data.pop("welcome", None) is not None
            return CommandResponse(
                "welcome", args, None,
                self.messages.render(
                    "strWelcomeMsgClearNotice" if existed else "strWelcomeMsgClearErr",
                    self._message_values(context),
                ),
            )
        if body.casefold() == "show" or not body:
            value = session.data.get("welcome")
            return CommandResponse(
                "welcome", args, value,
                value or self.messages.render("strWelcomeMsgEmpty", self._message_values(context)),
            )
        session.data["welcome"] = body
        return CommandResponse(
            "welcome", args, body,
            self.messages.render("strWelcomeMsgUpdateNotice", self._message_values(context)),
        )

    def _handle_draw(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        body = args.strip()
        hidden = metadata.get("hidden", False) or body.startswith("_") or body.casefold().startswith("h ")
        name = body[1:].strip() if body.startswith("_") else (body[1:].strip() if body.casefold().startswith("h ") else body)
        parts = name.split()
        if not parts:
            help_response = self._handle_help(context, "draw/deck", {"command": "help"})
            return CommandResponse("draw", args, {}, help_response.rendered)
        try:
            count = int(parts[1]) if len(parts) > 1 else 1
        except ValueError as error:
            raise CommandError(
                self.messages.render("strParaIllegal", self._message_values(context))
            ) from error
        if count == 0:
            raise CommandError(
                self.messages.render("strNumCannotBeZero", self._message_values(context))
            )
        if count < 0:
            raise CommandError(
                self.messages.render("strParaIllegal", self._message_values(context))
            )
        if parts[0] in session.decks:
            entries = []
            exhausted = False
            for _ in range(count):
                if session.decks[parts[0]].remaining == 0:
                    exhausted = True
                    break
                entries.append(session.draw(parts[0]))
            exhausted = exhausted or session.decks[parts[0]].remaining == 0
            if not entries:
                raise CommandError(
                    self.messages.render(
                        "strDeckRestEmpty",
                        self._message_values(context, {"deck_name": parts[0]}),
                    )
                )
        elif parts[0] in _PUBLIC_DECKS:
            remaining = list(_PUBLIC_DECKS[parts[0]])
            entries = []
            for _ in range(min(count, len(remaining))):
                entries.append(DeckEntry(remaining.pop(self.roller.randint(0, len(remaining) - 1))))
        else:
            raise CommandError(
                self.messages.render(
                    "strDeckNotFound",
                    self._message_values(context, {"deck_name": parts[0]}),
                )
            )
        result = [entry.value for entry in entries]
        actual_count = len(entries)
        values = self._message_values(
            context,
            {"res": "|".join(result), "cnt": actual_count},
        )
        rendered = self.messages.render(
            "strDrawHidden" if hidden else "strDrawCard",
            values,
        )
        if exhausted:
            rendered += "\n" + self.messages.render(
                "strDeckEmpty", self._message_values(context)
            )
        response_metadata = {"hidden": hidden, "count": actual_count}
        if hidden:
            response_metadata["private_rendered"] = self.messages.render("strDrawCard", values)
        return CommandResponse(
            "draw",
            args,
            result if count > 1 else result[0],
            rendered,
            response_metadata,
        )

    def _handle_deck(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        parts = args.strip().split(maxsplit=1)
        if not parts:
            help_response = self._handle_help(context, "draw/deck", {"command": "help"})
            return CommandResponse("deck", args, {}, help_response.rendered)
        operation = parts[0].casefold()
        value = parts[1].strip() if len(parts) == 2 else ""
        if "=" in operation:
            operation, inline_value = operation.split("=", 1)
            value = " ".join(item for item in (inline_value, value) if item)
        if operation == "show":
            if value and value in session.decks:
                result = {value: session.decks[value].to_dict()}
                deck = session.decks[value]
                rendered = self.messages.render(
                    "strDeckRestShow",
                    self._message_values(
                        context,
                        {
                            "deck_name": value,
                            "deck_rest": " | ".join(
                                deck.entries[index].value for index in deck._remaining
                            ),
                        },
                    ),
                )
            elif value:
                raise CommandError(
                    self.messages.render(
                        "strDeckNotFound",
                        self._message_values(context, {"deck_name": value}),
                    )
                )
            else:
                result = {name: deck.remaining for name, deck in session.decks.items()}
                rendered = self.messages.render(
                    "strDeckListShow" if result else "strDeckListEmpty",
                    self._message_values(
                        context,
                        {"res": " ".join(f"{name}[{remaining}]" for name, remaining in result.items())},
                    ),
                )
            return CommandResponse("deck", args, result, rendered)
        if operation == "clr":
            session.decks.clear()
            return CommandResponse(
                "deck", args, {},
                self.messages.render("strDeckListClr", self._message_values(context)),
            )
        if operation == "reset":
            if value not in session.decks:
                raise CommandError(
                    self.messages.render(
                        "strDeckNotFound", self._message_values(context, {"deck_name": value})
                    )
                )
            session.decks[value].reset()
            return CommandResponse(
                "deck", args, session.decks[value].remaining,
                self.messages.render(
                    "strDeckRestReset", self._message_values(context, {"deck_name": value})
                ),
            )
        if operation == "del":
            if value not in session.decks:
                raise CommandError(
                    self.messages.render(
                        "strDeckNotFound", self._message_values(context, {"deck_name": value})
                    )
                )
            del session.decks[value]
            return CommandResponse(
                "deck", args, {},
                self.messages.render("strDeckDelete", self._message_values(context, {"deck_name": value})),
            )
        if operation in {"new", "set"}:
            if "=" in value:
                name, raw_entries = (item.strip() for item in value.split("=", 1))
            else:
                tokens = value.split(maxsplit=1)
                if operation == "new":
                    name = tokens[0] if tokens else ""
                    raw_entries = tokens[1] if len(tokens) == 2 else name
                else:
                    name = tokens[0] if tokens else ""
                    raw_entries = value
            if operation == "set" and not raw_entries:
                raw_entries = name
            if operation == "set" and raw_entries.casefold().startswith("range"):
                range_tokens = raw_entries.split()
                if len(range_tokens) not in {2, 3, 4}:
                    raise CommandError(".deck set range lower upper [step]")
                try:
                    lower = int(range_tokens[1])
                    upper = int(range_tokens[2]) if len(range_tokens) >= 3 else 0
                    step = int(range_tokens[3]) if len(range_tokens) == 4 else 1
                except ValueError as error:
                    raise CommandError(
                        self.messages.render("strParaIllegal", self._message_values(context))
                    ) from error
                if lower == upper or step <= 0:
                    raise CommandError(
                        self.messages.render("strRangeEmpty", self._message_values(context))
                    )
                if lower > upper:
                    lower, upper = upper, lower
                if upper - lower > 1000 * step:
                    raise CommandError(
                        self.messages.render("strOutRange", self._message_values(context))
                    )
                entries = [DeckEntry(str(item)) for item in range(lower, upper + 1, step)]
                raw_entries = f"range{lower}~{entries[-1].value}"
            elif operation == "set" and raw_entries in _PUBLIC_DECKS:
                entries = [DeckEntry(item) for item in _PUBLIC_DECKS[raw_entries]]
            elif operation == "set" and raw_entries.casefold() == "member":
                return self._handle_adapter_boundary(context, args, {"command": "deck", "reason": "member list requires adapter input"})
            else:
                entries = [DeckEntry(item.strip()) for item in raw_entries.split("|") if item.strip()]
            if not name or not entries:
                raise CommandError(
                    self.messages.render("strDeckNewEmpty", self._message_values(context))
                )
            if name not in session.decks and len(session.decks) >= 10:
                raise CommandError(
                    self.messages.render("strDeckListFull", self._message_values(context))
                )
            if len(entries) > 256:
                raise CommandError(
                    self.messages.render("strDeckOversize", self._message_values(context))
                )
            session.configure_deck(name, entries)
            key = "strDeckNew" if operation == "new" else (
                "strDeckSet" if name == raw_entries else "strDeckSetRename"
            )
            return CommandResponse(
                "deck", args, name,
                self.messages.render(
                    key,
                    self._message_values(
                        context,
                        {"deck_name": name, "deck_cited": raw_entries},
                    ),
                ),
            )
        raise CommandError(f"unknown .deck operation: {operation}")

    def _handle_ank(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        parts = args.strip().split(maxsplit=1)
        if not parts:
            help_response = self._handle_help(context, "ak", {"command": "help"})
            return CommandResponse("ak", args, {}, help_response.rendered)
        operation = parts[0].casefold()
        value = parts[1].strip() if len(parts) == 2 else ""
        state = session.data.setdefault("ank", {"title": "", "options": []})
        if operation in {"new", "#"}:
            state["title"] = value
            state["options"] = []
        elif operation in {"add", "+"}:
            additions = [item.strip() for item in value.split("|") if item.strip()]
            if not additions:
                raise CommandError(
                    self.messages.render("strAkAddEmpty", self._message_values(context))
                )
            state["options"].extend(additions)
        elif operation in {"del", "-"}:
            try:
                index = int(value) - 1
            except ValueError as error:
                raise CommandError(
                    self.messages.render("strAkNumErr", self._message_values(context))
                ) from error
            if not 0 <= index < len(state["options"]):
                raise CommandError(
                    self.messages.render("strAkNumErr", self._message_values(context))
                )
            state["options"].pop(index)
        elif operation in {"get", "="}:
            if not state["options"]:
                raise CommandError(
                    self.messages.render("strAkOptEmptyErr", self._message_values(context))
                )
            selected = state["options"][self.roller.randint(0, len(state["options"]) - 1)]
            fork = state["title"]
            options = "\n".join(
                f"{index}. {option}" for index, option in enumerate(state["options"], start=1)
            )
            selected_index = state["options"].index(selected) + 1
            state["options"] = []
            return CommandResponse(
                "ak", args, selected,
                self.messages.render(
                    "strAkGet",
                    self._message_values(
                        context,
                        {"fork": fork, "li": options, "get": f"{selected_index}. {selected}"},
                    ),
                ),
            )
        elif operation == "clr":
            state["title"], state["options"] = "", []
        elif operation != "show":
            raise CommandError(f"unknown .ak operation: {operation}")
        options = "\n".join(
            f"{index}. {option}" for index, option in enumerate(state["options"], start=1)
        )
        if operation in {"new", "#"}:
            rendered = self.messages.render(
                "strAkForkNew", self._message_values(context, {"fork": state["title"]})
            )
        elif operation in {"add", "+"}:
            rendered = self.messages.render(
                "strAkAdd", self._message_values(context, {"fork": state["title"], "li": options})
            )
        elif operation in {"del", "-"}:
            rendered = self.messages.render(
                "strAkDel", self._message_values(context, {"fork": state["title"], "li": options})
            )
        elif operation == "clr":
            rendered = self.messages.render(
                "strAkClr", self._message_values(context, {"fork": state["title"]})
            )
        else:
            rendered = self.messages.render(
                "strAkShow", self._message_values(context, {"fork": state["title"], "li": options})
            )
        return CommandResponse("ak", args, dict(state), rendered)

    def _handle_rules(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        body = args.strip()
        if body.casefold().startswith("set"):
            rule = body[3:].strip()
            session.data["rules_default"] = rule or None
            key = "strRuleSet" if rule else "strRuleReset"
            return CommandResponse(
                metadata.get("command", "rules"), args, rule or None,
                self.messages.render(key, self._message_values(context, {"rule": rule or "COC"})),
            )
        if not body:
            raise CommandError(".rules requires a query or set [rule]")
        if ":" in body or "：" in body:
            rule, query = re.split(r"[:：]", body, maxsplit=1)
        else:
            rule, query = session.data.get("rules_default") or "COC", body
        if query.casefold().startswith("s "):
            query = query[2:].strip()
        result = {"rule": rule, "query": query.strip(), "found": False}
        return CommandResponse(
            metadata.get("command", "rules"), args, result,
            self.messages.render(
                "strRuleErr", self._message_values(context, {"err": "核心模块未内置词库"})
            ),
        )

    def _handle_log(
        self, context: MessageContext, args: str, metadata: dict[str, Any]
    ) -> CommandResponse:
        session = self._session_for(context)
        parts = args.strip().split(maxsplit=1)
        if not parts:
            help_response = self._handle_help(context, "log", {"command": "help"})
            return CommandResponse("log", args, {}, help_response.rendered)
        operation = parts[0].casefold()
        name = parts[1].strip() if len(parts) == 2 else ""
        log = session.data.get("log")
        if operation == "new":
            log = {"name": name or date.today().isoformat(), "enabled": True, "entries": []}
            session.data["log"] = log
            key = "strLogNew"
        elif operation == "on":
            if not log:
                log = {"name": name or date.today().isoformat(), "enabled": True, "entries": []}
                session.data["log"] = log
                key = "strLogNew"
            elif log.get("enabled"):
                key = "strLogOnAlready"
            else:
                log["enabled"] = True
                key = "strLogOn"
        elif operation == "off":
            if not log:
                raise CommandError(self.messages.render("strLogNullErr", self._message_values(context)))
            if not log.get("enabled"):
                key = "strLogOffAlready"
            else:
                log["enabled"] = False
                key = "strLogOff"
        elif operation == "end":
            if not log:
                raise CommandError(self.messages.render("strLogNullErr", self._message_values(context)))
            log["enabled"] = False
            log["ended"] = True
            key = "strLogEndEmpty"
        else:
            raise CommandError(f"unknown .log operation: {operation}")
        result = session.data.get("log", {"enabled": False})
        rendered = self.messages.render(
            key,
            self._message_values(context, {"game": {"log_name": result.get("name", "")}}),
        )
        return CommandResponse("log", args, result, rendered)

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

    def _message_values(
        self,
        context: MessageContext,
        values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nickname = self.identities.nicknames.resolve(context)
        card = self.identities.characters.resolve(context)
        result = {
            "nick": nickname,
            "pc": card.name if card is not None else nickname,
            "self": self.messages.get("self"),
            "uid": context.actor.user_id,
            "platform": context.actor.platform,
            "source": context.source.source_id,
        }
        if values:
            result.update(values)
        return result

    @staticmethod
    def _render_roulette_list(roulettes: dict[str, Any]) -> str:
        return "\n".join(
            f"D{sides}"
            for sides, value in sorted(roulettes.items(), key=lambda item: int(item[0]))
        )

    def _render_game_state(self, context: MessageContext, session: DiceSession) -> str:
        game_id = str(session.data.get("game_id", session.data.get("name", session.session_id)))
        if not session.data.get("game_active", False):
            return self.messages.render(
                "strGameVoidHere",
                self._message_values(context, {"game_id": game_id}),
            )
        lines = [f"桌号: {game_id}"]
        if "rule" in session.data:
            lines.append(f"规则: {session.data['rule']}")
        log = session.data.get("log")
        if isinstance(log, dict) and log.get("enabled"):
            lines.append(f"日志记录中:{log.get('name', '')}")
        if session.game_masters:
            lines.append("GM: " + " & ".join(sorted(actor.user_id for actor in session.game_masters)))
        if session.players:
            lines.append("PL:\n" + "\n".join(sorted(actor.user_id for actor in session.players)))
        if session.observers:
            lines.append("OB:\n" + "\n".join(sorted(actor.user_id for actor in session.observers)))
        if session.roulettes:
            lines.append("轮盘骰: D" + "/".join(str(face) for face in sorted(session.roulettes)))
        return "\n".join(lines)

    @staticmethod
    def _render_dnd_cards(cards: list[dict[str, Any]]) -> str:
        rendered: list[str] = []
        for attributes in cards:
            values = sorted(
                (int(value) for value in attributes.values() if isinstance(value, (int, float))),
                reverse=True,
            )
            rendered.append(
                "".join(f"{value:2d} /" for value in values) + f"总计{sum(values)}"
            )
        return "\n".join(rendered)

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
        if variant == 7:
            expressions = (
                ("力量", "3d6*5"),
                ("体质", "3d6*5"),
                ("体型", "(2d6+6)*5"),
                ("敏捷", "3d6*5"),
                ("外貌", "3d6*5"),
                ("智力", "(2d6+6)*5"),
                ("意志", "3d6*5"),
                ("教育", "(2d6+6)*5"),
                ("幸运", "3d6*5"),
            )
            attributes = {name: self.roller.roll(expression).total for name, expression in expressions}
            without_luck = sum(attributes[name] for name, _ in expressions[:-1])
            attributes["不含幸运合计"] = without_luck
            attributes["含幸运合计"] = without_luck + attributes["幸运"]
            attributes.update(self._coc7_derived_attributes(attributes))
            return attributes

        expressions = (
            ("力量", "3d6"),
            ("体质", "3d6"),
            ("体型", "2d6+6"),
            ("敏捷", "3d6"),
            ("外貌", "3d6"),
            ("智力", "2d6+6"),
            ("意志", "3d6"),
            ("教育", "3d6+3"),
        )
        attributes = {name: self.roller.roll(expression).total for name, expression in expressions}
        attributes["共计"] = sum(attributes.values())
        attributes["资产"] = self.roller.roll("1d10").total
        attributes.update(self._coc6_derived_attributes(attributes))
        return attributes

    @staticmethod
    def _coc7_derived_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
        strength = int(attributes["力量"])
        constitution = int(attributes["体质"])
        size = int(attributes["体型"])
        dexterity = int(attributes["敏捷"])
        power = int(attributes["意志"])
        strength_size = strength + size
        if strength_size <= 64:
            damage_bonus, build = "-2", -2
        elif strength_size <= 84:
            damage_bonus, build = "-1", -1
        elif strength_size <= 124:
            damage_bonus, build = "0", 0
        elif strength_size <= 164:
            damage_bonus, build = "1D4", 1
        elif strength_size <= 204:
            damage_bonus, build = "1d6", 2
        else:
            damage_bonus, build = "计算错误!", "计算错误"
        if dexterity < size and strength < size:
            movement = 7
        elif dexterity > size and strength > size:
            movement = 9
        else:
            movement = 8
        return {
            "理智": power,
            "生命值": (constitution + size) // 10,
            "魔法值": power // 5,
            "伤害奖励": damage_bonus,
            "体格": build,
            "移动力": movement,
        }

    @staticmethod
    def _coc6_derived_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
        strength = int(attributes["力量"])
        constitution = int(attributes["体质"])
        size = int(attributes["体型"])
        power = int(attributes["意志"])
        strength_size = strength + size
        if strength_size <= 12:
            damage_bonus = "-1D6"
        elif strength_size <= 16:
            damage_bonus = "-1D4"
        elif strength_size <= 24:
            damage_bonus = "0"
        elif strength_size <= 32:
            damage_bonus = "1D4"
        elif strength_size <= 40:
            damage_bonus = "1D6"
        else:
            damage_bonus = "计算错误!"
        return {
            "理智": power * 5,
            "灵感": int(attributes["智力"]) * 5,
            "幸运": power * 5,
            "知识": int(attributes["教育"]) * 5,
            "生命值": math.ceil((constitution + size) / 2),
            "魔法值": power,
            "伤害奖励": damage_bonus,
        }

    @staticmethod
    def _render_coc_attributes(
        attributes: dict[str, Any], variant: int, detailed: bool, count: int
    ) -> str:
        if variant == 7 and not detailed:
            names = ("力量", "体质", "体型", "敏捷", "外貌", "智力", "意志", "教育", "幸运")
            values = " ".join(f"{name}:{attributes[name]}" for name in names)
            return f"{values} 共计:{attributes['不含幸运合计']}/{attributes['含幸运合计']}"
        if variant == 6 and not detailed:
            names = ("力量", "体质", "体型", "敏捷", "外貌", "智力", "意志", "教育")
            values = " ".join(
                f"{name}:{attributes[name]}" + ("  " if count != 1 and attributes[name] < 10 else "")
                for name in names
            )
            return f"{values} 共计:{attributes['共计']} 资产:{attributes['资产']}"
        if variant == 7:
            return "\n".join(
                (
                    f"力量STR=3D6*5={attributes['力量']}/{attributes['力量'] // 2}/{attributes['力量'] // 5}",
                    f"体质CON=3D6*5={attributes['体质']}/{attributes['体质'] // 2}/{attributes['体质'] // 5}",
                    f"体型SIZ=(2D6+6)*5={attributes['体型']}/{attributes['体型'] // 2}/{attributes['体型'] // 5}",
                    f"敏捷DEX=3D6*5={attributes['敏捷']}/{attributes['敏捷'] // 2}/{attributes['敏捷'] // 5}",
                    f"外貌APP=3D6*5={attributes['外貌']}/{attributes['外貌'] // 2}/{attributes['外貌'] // 5}",
                    f"智力INT=(2D6+6)*5={attributes['智力']}/{attributes['智力'] // 2}/{attributes['智力'] // 5}",
                    f"意志POW=3D6*5={attributes['意志']}/{attributes['意志'] // 2}/{attributes['意志'] // 5}",
                    f"教育EDU=(2D6+6)*5={attributes['教育']}/{attributes['教育'] // 2}/{attributes['教育'] // 5}",
                    f"幸运LUCK=3D6*5={attributes['幸运']}",
                    f"共计:{attributes['不含幸运合计']}/{attributes['含幸运合计']}",
                    f"理智SAN=POW={attributes['理智']}",
                    f"生命值HP=(SIZ+CON)/10={attributes['生命值']}",
                    f"魔法值MP=POW/5={attributes['魔法值']}",
                    f"伤害奖励DB={attributes['伤害奖励']}",
                    f"体格={attributes['体格']}",
                    f"移动力MOV={attributes['移动力']}",
                )
            )
        return "\n".join(
            (
                f"力量STR=3D6={attributes['力量']}",
                f"体质CON=3D6={attributes['体质']}",
                f"体型SIZ=2D6+6={attributes['体型']}",
                f"敏捷DEX=3D6={attributes['敏捷']}",
                f"外貌APP=3D6={attributes['外貌']}",
                f"智力INT=2D6+6={attributes['智力']}",
                f"意志POW=3D6={attributes['意志']}",
                f"教育EDU=3D6+3={attributes['教育']}",
                f"共计:{attributes['共计']}",
                f"理智SAN=POW*5={attributes['理智']}",
                f"灵感IDEA=INT*5={attributes['灵感']}",
                f"幸运LUCK=POW*5={attributes['幸运']}",
                f"知识KNOW=EDU*5={attributes['知识']}",
                f"生命值HP=(CON+SIZ)/2={attributes['生命值']}",
                f"魔法值MP=POW={attributes['魔法值']}",
                f"伤害奖励DB={attributes['伤害奖励']}",
                f"资产=1D10={attributes['资产']}",
            )
        )

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
        if body.startswith("简单"):
            return 2.0, body[2:].strip()
        if body.startswith("极限"):
            return 0.2, body[2:].strip()
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
    def _split_status_assignments(body: str) -> list[str]:
        tokens: list[str] = []
        for token in body.split():
            if any(operator in token for operator in (":", "=", "+", "-", "&")):
                tokens.append(token)
                continue
            matches = re.findall(r"([^\d\s]+?)(\d+)(?=[^\d\s]|$)", token)
            if matches and "".join(name + value for name, value in matches) == token:
                tokens.extend(name + value for name, value in matches)
            else:
                tokens.append(token)
        return tokens

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
    def _render_card_attributes(card: CharacterCard) -> str:
        visible = CommandRouter._visible_attributes(card.attributes)
        if not visible:
            return ""
        if card.system.casefold() in {"coc", "coc7"}:
            return CommandRouter._render_coc7_card_attributes(visible)
        return " ".join(f"{name}:{value}" for name, value in visible.items())

    @staticmethod
    def _render_coc7_card_attributes(attributes: dict[str, Any]) -> str:
        groups = (
            ("职业", "年龄", "性别", "住地", "出身", "时代"),
            ("力量", "体质", "体型", "敏捷", "外貌", "智力", "意志", "教育"),
            ("生命", "理智", "魔法", "幸运"),
            ("身体状态", "精神状态"),
            ("DB", "闪避", "护甲"),
        )
        aliases = {
            "生命": ("生命", "生命值", "hp"),
            "魔法": ("魔法", "魔法值", "mp"),
            "DB": ("DB", "伤害奖励"),
        }
        rendered_groups: list[str] = []
        used: set[str] = set()
        for group in groups:
            parts: list[str] = []
            for name in group:
                candidates = aliases.get(name, (name,))
                key = next((item for item in candidates if item in attributes), None)
                if key is None and name == "闪避" and isinstance(attributes.get("敏捷"), (int, float)):
                    value = int(attributes["敏捷"]) // 2
                elif key is None:
                    continue
                else:
                    value = attributes[key]
                    used.add(key)
                separator = "=" if name.startswith("&") else ":"
                parts.append(f"{name}{separator}{value}")
            if parts:
                rendered_groups.append(" ".join(parts))
        rest = "".join(
            f"{key}:{value}" + (" " if isinstance(value, (int, float)) else "\t")
            for key, value in attributes.items()
            if key not in used and key not in {"体格", "移动力"}
        ).rstrip()
        if rest:
            rendered_groups.append(rest)
        return "\n".join(rendered_groups)

    @staticmethod
    def _visible_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in attributes.items() if not key.startswith("__")}

    @staticmethod
    def _render_card(card: CharacterCard, detailed: bool) -> str:
        if detailed:
            return f"[{card.card_id}] {card.name}<{card.system}>\n{CommandRouter._render_attributes(card.attributes)}"
        visible = CommandRouter._visible_attributes(card.attributes)
        return f"[{card.card_id}] {card.name}<{card.system}> {CommandRouter._render_attributes(visible)}"

    def _render_roll(
        self,
        context: MessageContext,
        response: RollResponse,
        metadata: dict[str, Any],
    ) -> str:
        reason = response.request.reason
        values = self._message_values(
            context,
            {
                "pc": response.card_name or response.display_name,
                "res": response.result.render_c(),
                "reason": reason or "",
                "dice_exp": response.result.normalized_expression,
                "turn": metadata.get("repeat", 1),
            },
        )
        key = "strRollDiceReason" if reason else "strRollDice"
        return self.messages.render(key, values)

    def _render_checks(
        self,
        context: MessageContext,
        checks: list[CheckResult],
        skill: str,
        reason: str | None,
        hidden: bool,
        metadata: dict[str, Any],
    ) -> str:
        if hidden:
            return self.messages.render(
                "strRollSkillHidden",
                self._message_values(context, {"attr": skill, "reason": reason or ""}),
            )
        header_key = "strRollSkillReason" if reason else "strRollSkill"
        header = self.messages.render(
            header_key,
            self._message_values(context, {"attr": skill, "reason": reason or ""}),
        )
        results = []
        for check in checks:
            values = self._message_values(
                context,
                {
                    "res": self._render_check_roll(check),
                    "target": check.target,
                    "rank": self._success_rank(check.success_level),
                },
            )
            result_key = {
                "critical": "strCriticalSuccess" if metadata.get("repeat", 1) > 1 else "strRollCriticalSuccess",
                "extreme_success": "strExtremeSuccess" if metadata.get("repeat", 1) > 1 else "strRollExtremeSuccess",
                "hard_success": "strHardSuccess" if metadata.get("repeat", 1) > 1 else "strRollHardSuccess",
                "regular_success": "strSuccess" if metadata.get("repeat", 1) > 1 else "strRollRegularSuccess",
                "failure": "strFailure" if metadata.get("repeat", 1) > 1 else "strRollFailure",
                "fumble": "strFumble" if metadata.get("repeat", 1) > 1 else "strRollFumble",
            }.get(check.success_level, "strRollFailure")
            results.append(
                f"{self._render_check_roll(check)}/{check.target} "
                f"{self.messages.render(result_key, values)}"
            )
        return header + ("\n" if len(results) > 1 else "") + "\n".join(results)

    @staticmethod
    def _render_check_roll(check: CheckResult) -> str:
        return check.roll.render_c()

    @staticmethod
    def _success_rank(success_level: str) -> int:
        return {
            "fumble": 0,
            "failure": 1,
            "regular_success": 1,
            "hard_success": 3,
            "extreme_success": 4,
            "critical": 5,
        }.get(success_level, 0)
