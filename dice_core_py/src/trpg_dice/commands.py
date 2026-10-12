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
from .models import (
    CheckResult,
    DiceTermResult,
    MessageContext,
    RollRequest,
    RollResponse,
    RollResult,
)
from .messages import MessageCatalog
from .profiles import CharacterCard, IdentityServices
from .roller import DiceRoller, coc_success_level
from .session import DiceSession
from .special import Deck, DeckEntry, Roulette


_TEMPORARY_INSANITY = (
    "",
    "失忆：在{dur}轮之内，{pc}会发现自己只记得最后身处的安全地点，却没有任何来到这里的记忆。",
    "假性残疾：{pc}陷入了心理性的失明、失聪或躯体缺失感中，持续{dur}轮。",
    "暴力倾向：{pc}陷入了六亲不认的暴力行为中，对周围的敌人与友方进行着无差别的攻击，持续{dur}轮。",
    "偏执：{pc}陷入了严重的偏执妄想之中。有人在暗中窥视着他们，同伴中有人背叛了他们，没有人可以信任，万事皆虚。持续{dur}轮。",
    "人际依赖：{pc}因为一些原因而将他人误认为了他重要的人并且努力的会与那个人保持那种关系，持续{dur}轮。",
    "昏厥：{pc}当场昏倒，昏迷状态持续{dur}轮。",
    "逃避行为：{pc}会用任何的手段试图逃离现在所处的位置，状态持续{dur}轮。",
    "竭嘶底里：{pc}表现出大笑，哭泣，嘶吼，害怕等的极端情绪表现，持续{dur}轮。",
    "恐惧：{pc}陷入对某一事物的恐惧之中，持续{dur}轮。\n{detail_roll}\n具体恐惧症：{detail}",
    "躁狂：{pc}由于某种诱因进入躁狂状态，症状持续{dur}轮。\n{detail_roll}\n具体躁狂症：{detail}",
)

_LONG_INSANITY = (
    "",
    "失忆：在{dur}小时后，{pc}回过神来，发现自己身处一个陌生的地方，并忘记了自己是谁。记忆会随时间恢复。",
    "被窃：{pc}在{dur}小时后恢复清醒，发觉自己被盗，身体毫发无损。",
    "遍体鳞伤：{pc}在{dur}小时后恢复清醒，发现自己身上满是拳痕和瘀伤。生命值减少到疯狂前的一半。",
    "暴力倾向：{pc}陷入强烈的暴力与破坏欲之中，持续{dur}小时。",
    "极端信念：在{dur}小时之内，{pc}会采取极端和疯狂的表现手段展示他们的思想信念之一。",
    "重要之人：在{dur}小时中，{pc}将不顾一切地接近重要的那个人，并为关系做出行动。",
    "被收容：{dur}小时后，{pc}在精神病院病房或警察局牢房中回过神来。",
    "逃避行为：{dur}小时后，{pc}恢复清醒时发现自己在很远的地方。",
    "恐惧：{pc}患上一个新的恐惧症，会在{dur}小时后恢复正常。\n{detail_roll}\n具体恐惧症：{detail}",
    "躁狂：{pc}患上一个新的躁狂症，在{dur}小时后恢复理智。\n{detail_roll}\n具体躁狂症：{detail}",
)

_INSANITY_DETAILS = (
    "洗澡恐惧症：对于洗涤或洗澡的恐惧。",
    "恐高症：对于身处高处的恐惧。",
    "幽闭恐惧症：对于处在封闭空间中的恐惧。",
    "恐犬症：对狗的恐惧。",
    "恐水症：对水的恐惧。",
    "恐惧黑暗：对黑暗或夜晚的恐惧。",
    "人群恐惧症：对于人群的恐惧。",
    "恐蛇症：对蛇的恐惧。",
    "恐火症：对火的恐惧。",
    "恐惧死亡：对死亡或尸体的恐惧。",
)

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
            values = self._message_values(context, metadata)
            if metadata.get("short"):
                result_text = "{ " + ",".join(str(response.result.total) for response in responses) + " }"
            else:
                result_text = ", ".join(response.result.render() for response in responses)
            values.update(
                {
                    "turn": repeat,
                    "dice_exp": responses[0].result.normalized_expression,
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
                        "dice_exp": responses[0].result.normalized_expression,
                        "res": ", ".join(response.result.render() for response in responses),
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
        session.data.setdefault("roulette_history", []).append(value)
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
            requested = ""
            if card is None:
                result: dict[str, Any] = {}
            else:
                requested = body[4:].strip()
                if not requested:
                    result = self._visible_attributes(card.attributes)
                else:
                    key = self._attribute_key(card.attributes, requested)
                    result = {} if key not in card.attributes else {requested: card.attributes[key]}
            if not result:
                rendered = self._render_attributes(result)
            elif requested:
                rendered = self.messages.render(
                    "strProp",
                    self._message_values(context, {"attr": requested, "val": next(iter(result.values()))}),
                )
            else:
                rendered = self.messages.render(
                    "strPropList",
                    self._message_values(
                        context,
                        {"char": card.name if card else self.identities.nicknames.resolve(context), "show": self._render_attributes(result)},
                    ),
                )
            return CommandResponse("st", args, result, rendered)

        card = card or self._ensure_card(context)
        if body.casefold() == "clr":
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
            names = body[4:].split()
            attributes = dict(card.attributes)
            for name in names:
                attributes.pop(self._attribute_key(attributes, name), None)
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
        if not body:
            result = self._visible_attributes(card.attributes)
            return CommandResponse("st", args, result, self._render_attributes(result))

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
        self._record_check_stat(context, updated, roll.total, int(current))
        result = {
            "roll": roll,
            "current": current,
            "success": success,
            "loss": loss,
            "remaining": remaining,
            "card": updated,
        }
        from .roller import coc_success_level

        success_level = coc_success_level(roll.total, current, int(self._session_for(context).data.get("coc_rule", 0)))
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
                    "change": loss,
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
        rendered = self.messages.render(
            "strRollInit",
            self._message_values(
                context,
                {"char": name, "res": "\n".join(f"{entry['name']}: {entry['value']}" for entry in entries)},
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
        operation = args.strip().casefold() or "join"
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
            result = [item.to_dict() for item in sorted(session.observers, key=lambda item: item.key)]
            if result:
                rendered = self.messages.render("strObList", self._message_values(context, {"res": "\n".join(item["user_id"] for item in result)}))
            else:
                rendered = self.messages.render("strObListEmpty", self._message_values(context))
        elif operation == "clr":
            session.observers.clear()
            result = []
            rendered = self.messages.render("strObListClr", self._message_values(context))
        elif operation in {"on", "off"}:
            session.data["observer_enabled"] = operation == "on"
            result = {"enabled": session.data["observer_enabled"]}
            rendered = self.messages.render(
                "strObOn" if operation == "on" else "strObOff",
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
        operation = parts[0].casefold() if parts else "state"
        value = parts[1].strip() if len(parts) == 2 else ""
        if operation == "new":
            session.sources.clear()
            session.game_masters.clear()
            session.players.clear()
            session.observers.clear()
            session.data.clear()
            session.data["name"] = value or session.session_id
            session.add_source(context.source)
            session.add_gm(context.actor)
            return CommandResponse("game", args, {"session_id": session.session_id, "created": True}, "已创建新的跑团会话")
        if operation == "master":
            changed = session.add_gm(context.actor)
            return CommandResponse("game", args, {"changed": changed}, "已成为主持人" if changed else "你已经是主持人")
        if operation == "join":
            changed = session.add_player(context.actor)
            return CommandResponse("game", args, {"changed": changed}, "已加入跑团" if changed else "你已经加入跑团")
        if operation == "exit":
            changed = session.remove_player(context.actor) or session.remove_gm(context.actor)
            return CommandResponse("game", args, {"changed": changed}, "已退出跑团" if changed else "你不在跑团中")
        if operation in {"close", "over"}:
            session.data["closed"] = True
            return CommandResponse("game", args, {"closed": True}, "跑团会话已关闭")
        if operation == "open":
            session.data["closed"] = False
            if value:
                session.data["game_id"] = value
            return CommandResponse("game", args, {"closed": False}, "跑团会话已打开")
        if operation == "set":
            if "=" not in value:
                raise CommandError(".game set expects key=value")
            key, item = (part.strip() for part in value.split("=", 1))
            try:
                parsed: Any = json.loads(item)
            except json.JSONDecodeError:
                parsed = item
            session.data[key] = parsed
            return CommandResponse("game", args, {key: parsed}, f"已设置跑团参数：{key}={parsed}")
        if operation == "call":
            players = sorted(session.players, key=lambda item: item.key)
            result = [actor.to_dict() for actor in players]
            return CommandResponse("game", args, result, "\n".join(actor.user_id for actor in players) or "没有已加入的玩家")
        if operation == "state":
            result = session.to_dict()
            return CommandResponse("game", args, result, json.dumps(result, ensure_ascii=False, sort_keys=True))
        if operation == "rou":
            rou_parts = value.split()
            action = rou_parts[0].casefold() if rou_parts else "show"
            if action in {"clr", "reset"}:
                if action == "clr":
                    session.roulettes.clear()
                    session.data.pop("roulette_history", None)
                    return CommandResponse("game", args, {}, "轮盘骰已清空")
                for roulette in session.roulettes.values():
                    roulette.reset()
                session.data["roulette_history"] = []
                return CommandResponse("game", args, session.to_dict()["roulettes"], "轮盘骰已重置")
            if action == "hist":
                history = list(session.data.get("roulette_history", []))
                return CommandResponse("game", args, history, "\n".join(map(str, history)) or "轮盘骰暂无记录")
            match = re.fullmatch(r"(\d+)(?:\*(\d+))?", action)
            if match:
                sides = int(match.group(1))
                copies = int(match.group(2) or "1")
                if sides <= 0 or copies <= 0 or sides * copies > 100:
                    raise CommandError(".game rou requires positive sides/copies with total at most 100")
                roulette = session.configure_roulette(sides, copies)
                session.data["roulette_history"] = []
                return CommandResponse("game", args, roulette.to_dict(), f"已设置{copies}组D{sides}轮盘骰")
            if action == "show":
                result = {str(sides): roulette.to_dict() for sides, roulette in session.roulettes.items()}
                return CommandResponse("game", args, result, json.dumps(result, ensure_ascii=False, sort_keys=True))
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
        if not 1 <= count <= 10:
            raise CommandError(".name count must be in 1..10")
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
        if body.casefold() == "clr":
            result = self.identities.nicknames.clear(context.actor)
            return CommandResponse("nn", args, result, self.messages.render("strNameClr", self._message_values(context, {"old_nick": ""})))
        if body.casefold() == "del" or not body:
            source = None if context.source.kind == "private" else context.source
            result = self.identities.nicknames.remove(context.actor, source)
            return CommandResponse("nn", args, result, self.messages.render("strNameDel", self._message_values(context, {"old_nick": result or ""})))
        if body.casefold() == "nnn" or body.casefold().startswith("nnn "):
            kind = body[3:].strip().casefold() or "all"
            body = self._random_names(kind, 1)[0]
        elif body.casefold().startswith("n "):
            body = body[2:].strip()
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
            return self._render_card_statistics(context, args, current)
        if operation == "type":
            if not value:
                result = {"attr": "模板类", "val": current.system if current else "generic"}
                return CommandResponse("pc", args, result, f"模板类：{result['val']}")
            if current is None:
                raise CommandError("no current character card")
            updated = self.identities.characters.update(
                context.actor, current.card_id, system=value
            )
            return CommandResponse("pc", args, updated, f"人物卡模板已修改为：{value}")
        if operation == "temp":
            if current is None:
                raise CommandError("no current character card")
            result = {"system": current.system, "attributes": dict(current.attributes)}
            return CommandResponse("pc", args, result, self._render_attributes(result["attributes"]))
        if operation == "tojson":
            card = self._card_by_ref(context, value) if value else current
            if card is None:
                return CommandResponse("pc", args, {}, "无当前人物卡")
            result = card.to_dict()
            return CommandResponse("pc", args, result, json.dumps(result, ensure_ascii=False, sort_keys=True))
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

    def _render_card_statistics(
        self,
        context: MessageContext,
        args: str,
        card: CharacterCard | None,
    ) -> CommandResponse:
        if card is None:
            return CommandResponse("pc", args, {}, "暂无掷骰统计")
        face = self._default_sides(card)
        attributes = card.attributes
        dice_key = f"__StatD{face}"
        count = int(attributes.get(f"{dice_key}Cnt", 0))
        checks = int(attributes.get("__StatRcCnt", 0))
        if count <= 0 and checks <= 0:
            return CommandResponse("pc", args, {}, "暂无掷骰统计")
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
        return CommandResponse("pc", args, result, "\n".join(lines))

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
        symptom_roll = self.roller.roll("d10").total
        duration_roll = self.roller.roll("d10").total
        details: dict[str, Any] = {}
        if symptom_roll in {9, 10}:
            detail_roll = self.roller.roll("d100").total
            details = {
                "detail_roll": f"1D100={detail_roll}",
                "detail": _INSANITY_DETAILS[(detail_roll - 1) % len(_INSANITY_DETAILS)],
            }
        template = (_TEMPORARY_INSANITY if temporary else _LONG_INSANITY)[symptom_roll]
        symptom = template.format(
            pc=self.identities.characters.resolve(context).name
            if self.identities.characters.resolve(context)
            else self.identities.nicknames.resolve(context),
            nick=self.identities.nicknames.resolve(context),
            dur=duration_roll,
            detail_roll=details.get("detail_roll", ""),
            detail=details.get("detail", ""),
        )
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
        success = roll.total > current
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
            return CommandResponse(
                "me",
                args,
                session.data["me_enabled"],
                self.messages.render(
                    "strMeOn" if session.data["me_enabled"] else "strMeOff",
                    self._message_values(context),
                ),
            )
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
        if not parts:
            raise CommandError(".draw requires a deck name")
        count = int(parts[1]) if len(parts) > 1 else 1
        if count < 1:
            raise CommandError("draw count must be positive")
        if parts[0] in session.decks:
            entries = []
            for _ in range(count):
                if session.decks[parts[0]].remaining == 0:
                    break
                entries.append(session.draw(parts[0]))
            if not entries:
                raise CommandError(f"deck {parts[0]!r} is empty")
        elif parts[0] in _PUBLIC_DECKS:
            remaining = list(_PUBLIC_DECKS[parts[0]])
            entries = []
            for _ in range(min(count, len(remaining))):
                entries.append(DeckEntry(remaining.pop(self.roller.randint(0, len(remaining) - 1))))
        else:
            raise CommandError(f"deck {parts[0]!r} does not exist")
        result = [entry.value for entry in entries]
        actual_count = len(entries)
        values = self._message_values(
            context,
            {"res": "、".join(result), "cnt": actual_count},
        )
        rendered = self.messages.render(
            "strDrawHidden" if hidden else "strDrawCard",
            values,
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
        if operation == "del":
            if value not in session.decks:
                raise CommandError(f"deck {value!r} does not exist")
            del session.decks[value]
            return CommandResponse("deck", args, {}, f"牌堆 {value} 已删除")
        if operation in {"new", "set"}:
            if "=" in value:
                name, raw_entries = (item.strip() for item in value.split("=", 1))
            else:
                tokens = value.split(maxsplit=1)
                name = tokens[0] if tokens else ""
                raw_entries = value if operation == "set" else (tokens[1] if len(tokens) == 2 else "")
            if operation == "set" and not raw_entries:
                raw_entries = name
            if operation == "set" and raw_entries.casefold().startswith("range"):
                range_tokens = raw_entries.split()
                if len(range_tokens) != 3:
                    raise CommandError(".deck set range lower upper")
                lower, upper = (int(item) for item in range_tokens[1:])
                if lower > upper:
                    lower, upper = upper, lower
                entries = [DeckEntry(str(item)) for item in range(lower, upper + 1)]
            elif operation == "set" and raw_entries in _PUBLIC_DECKS:
                entries = [DeckEntry(item) for item in _PUBLIC_DECKS[raw_entries]]
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
            return CommandResponse(metadata.get("command", "rules"), args, rule or None, f"默认规则：{rule or 'COC'}")
        if not body:
            raise CommandError(".rules requires a query or set [rule]")
        if ":" in body or "：" in body:
            rule, query = re.split(r"[:：]", body, maxsplit=1)
        else:
            rule, query = session.data.get("rules_default") or "COC", body
        if query.casefold().startswith("s "):
            query = query[2:].strip()
        result = {"rule": rule, "query": query.strip(), "found": False}
        return CommandResponse(metadata.get("command", "rules"), args, result, f"规则查询（{rule}）：{query.strip()}，核心模块未内置词库")

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
                "res": response.result.render(),
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
        if len(check.roll.terms) == 1:
            term = check.roll.terms[0]
            if term.kind in {"bonus", "penalty"}:
                label = "奖励骰" if term.kind == "bonus" else "惩罚骰"
                detail = " ".join(str(value) for value in term.extra_tens)
                return f"{term.notation}={term.base_roll}[{label}:{detail}]={term.subtotal}"
        return check.roll.render()

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
