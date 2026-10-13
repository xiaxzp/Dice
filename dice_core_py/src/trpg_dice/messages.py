from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .storage import JsonStore


DEFAULT_MESSAGES: dict[str, str] = {
    "strSelfName": "",
    "strSelfCall": "&strSelfName",
    "strSelfNick": "&strSelfName",
    "self": "&strSelfCall",
    "strRollDice": "{pc}掷骰: {res}",
    "strRollDiceReason": "{pc}掷骰 {reason}: {res}",
    "strRollMultiDice": "{pc}掷骰{turn}次: {dice_exp}={res}",
    "strRollMultiDiceReason": "{pc}掷骰{turn}次{reason}: {dice_exp}={res}",
    "strRollHidden": "{pc}进行了一次暗骰",
    "strRollTurn": "{pc}的掷骰轮数: {turn}轮",
    "strRollSkill": "{pc}进行{attr}检定：",
    "strRollSkillReason": "由于{reason} {pc}进行{attr}检定：",
    "strRollSkillHidden": "{pc}进行了一次暗中{attr}检定√",
    "strRollCriticalSuccess": "大成功！",
    "strRollExtremeSuccess": "极难成功",
    "strRollHardSuccess": "困难成功",
    "strRollRegularSuccess": "成功",
    "strRollFailure": "失败",
    "strRollFumble": "大失败！",
    "strCriticalSuccess": "大成功!",
    "strExtremeSuccess": "极难成功",
    "strHardSuccess": "困难成功",
    "strSuccess": "成功",
    "strFailure": "失败",
    "strFumble": "大失败！",
    "strSanityRoll": (
        "{pc}的San Check：\n{res} "
        "{grade:rank?2={strSuccess}&1={strFailure}&0={strFumble}}\n"
        "{case:loss?0=无理智损失√&else=理智减少{change}->剩余{final}}"
    ),
    "strEnRoll": "{pc}的{attr}增强或成长检定：\n{res}",
    "strEnRollFailure": "{strEnRoll}\n{pc}的{attr}变化{change}点，当前为{final}点",
    "strEnRollSuccess": "{strEnRoll}\n{pc}的{attr}增加{change}点，当前为{final}点",
    "strEnRollNotChange": "{strEnRoll}\n{pc}的{attr}值没有变化",
    "strEnDefaultName": "属性或技能",
    "strRollInit": "{char}的先攻骰点：{res}",
    "strNameGenerator": "{pc}的随机名称：{res}",
    "strDrawCard": "来看看{pc}抽到了什么：{res}",
    "strDrawHidden": "{pc}抽了{cnt}张手牌√",
    "strJrrp": "{nick}今天的人品值是: {res}",
    "strTempInsane": "{pc}的疯狂发作-临时症状:\n{res}",
    "strLongInsane": "{pc}的疯狂发作-总结症状:\n{res}",
    "strMeOn": "成功在这里启用{self}的.me命令√",
    "strMeOff": "成功在这里禁用{self}的.me命令√",
    "strBotOn": "成功开启{self}√",
    "strBotOff": "成功关闭{self}√",
    "strBotOnAlready": "{self}已经处于开启状态!",
    "strBotOffAlready": "{self}已经处于关闭状态!",
    "strBotPrivate": ".bot on/off 仅支持群聊",
    "strObOn": "{self}已在本桌启用旁观√",
    "strObOff": "{self}已在本桌禁用旁观√",
    "strObEnter": "{nick}成功加入{self}的旁观√",
    "strObExit": "{nick}成功退出{self}的旁观√",
    "strObEnterAlready": "{nick}已经处于{self}的旁观模式!",
    "strObExitAlready": "{nick}没有加入{self}的旁观模式!",
    "strObList": "本桌{self}的旁观者有:{res}",
    "strObListEmpty": "本桌{self}暂无旁观者",
    "strObListClr": "{self}已清空旁观者√",
    "strSetDefaultDice": "{self}已将{pc}的默认骰设置为D{default}√",
    "strProp": "{pc}的{attr}为{val}",
    "strPropList": "{nick}的{char}属性列表为：{show}",
    "strPropCleared": "{self}已清空{char}的所有属性√",
    "strPropDeleted": "已删除{pc}的{attr}√",
    "strSetPropSuccess": "{self}已为{pc}录入{cnt}条属性√",
    "strNameSet": "{self}已将{old_nick}改称为{new_nick}√",
    "strNameDel": "{self}已删除{old_nick}在当前窗口的称呼√",
    "strNameClr": "{self}已清空{old_nick}的所有称呼√",
    "strPcCardShow": "{nick}的<{type}>{char}：{show}",
}


class MessageCatalog:
    """Persistent message templates compatible with Dice!'s CustomMsg."""

    def __init__(self, root: str | Path, *, random_int: Callable[[int, int], int] | None = None) -> None:
        self.store = JsonStore(root)
        self.path = "config/custom_messages.json"
        self._random_int = random_int
        value = self.store.read(self.path)
        self.custom = {
            str(key): str(text)
            for key, text in (value or {}).items()
            if isinstance(key, str) and isinstance(text, str)
        }

    def get(self, key: str) -> str:
        return self.custom.get(key, DEFAULT_MESSAGES.get(key, ""))

    def set(self, key: str, value: str) -> str:
        normalized_key = str(key).strip()
        if not normalized_key:
            raise ValueError("message key must not be empty")
        self.custom[normalized_key] = str(value)
        self._save()
        return self.custom[normalized_key]

    def reset(self, key: str) -> bool:
        existed = str(key) in self.custom
        self.custom.pop(str(key), None)
        if existed:
            self._save()
        return existed

    def keys(self) -> list[str]:
        return sorted(set(DEFAULT_MESSAGES) | set(self.custom))

    def render(self, key: str, values: Mapping[str, Any] | None = None) -> str:
        context = dict(values or {})
        text = self.get(key)
        if text.startswith("&"):
            return self._render_reference(text[1:], context, {key})
        return self._render(text, context, {key})

    def _save(self) -> None:
        self.store.write(self.path, dict(self.custom))

    def _render(self, text: str, values: dict[str, Any], stack: set[str]) -> str:
        return self._render_text(str(text), values, stack)

    def _render_text(self, text: str, values: dict[str, Any], stack: set[str]) -> str:
        result: list[str] = []
        position = 0
        while position < len(text):
            opening = text.find("{", position)
            if opening < 0:
                result.append(text[position:])
                break
            result.append(text[position:opening])
            closing = self._find_closing(text, opening)
            if closing < 0:
                result.append(text[opening:])
                break
            token = text[opening + 1 : closing]
            result.append(self._render_token(token, values, stack))
            position = closing + 1
        return "".join(result)

    @staticmethod
    def _find_closing(text: str, opening: int) -> int:
        depth = 1
        for position in range(opening + 1, len(text)):
            if text[position] == "{":
                depth += 1
            elif text[position] == "}":
                depth -= 1
                if depth == 0:
                    return position
        return -1

    def _render_token(self, token: str, values: dict[str, Any], stack: set[str]) -> str:
        if token == "br":
            return "\n"
        if token == "FormFeed":
            return "\f"
        if ":" not in token:
            return self._render_reference(token, values, stack)

        method, parameter = token.split(":", 1)
        if method == "sample":
            choices = self._split_top_level(parameter, "|")
            if not choices:
                return ""
            index = self._randint(0, len(choices) - 1)
            return self._render_text(choices[index], values, stack)
        if method == "ran":
            bounds = parameter.split("~", 1)
            if len(bounds) != 2:
                return ""
            try:
                lower = int(self._render_text(bounds[0], values, stack))
                upper = int(self._render_text(bounds[1], values, stack))
                if lower >= upper:
                    return ""
                return str(self._randint(lower, upper))
            except ValueError:
                return ""
        if method in {"case", "grade"}:
            return self._render_conditional(method, parameter, values, stack)
        if method == "var":
            return self._render_variable(parameter, values, stack)
        if method == "len":
            resolved = self._resolve(parameter, values)
            return str(len("" if resolved is None else str(resolved)))
        if method in {"print", "at"}:
            resolved = self._resolve(parameter, values)
            if resolved is None:
                resolved = self._resolve("uid", values) if method == "at" else None
            if resolved is None:
                return ""
            return f"@{resolved}" if method == "at" else str(resolved)
        if method == "help":
            resolved = self._resolve(parameter, values)
            return "" if resolved is None else str(resolved)
        if method == "expired":
            resolved = self._resolve(parameter, values)
            try:
                return "1" if float(resolved) < time.time() else "0"
            except (TypeError, ValueError):
                return "1"
        if method == "wait":
            return ""
        return "{" + token + "}"

    def _render_reference(self, token: str, values: dict[str, Any], stack: set[str]) -> str:
        normalized = token.strip()
        if normalized.startswith("&"):
            normalized = normalized[1:].strip()
        value = self._resolve(normalized, values)
        if value is None:
            return "{" + token + "}"
        if normalized in DEFAULT_MESSAGES or normalized in self.custom or normalized in values:
            if normalized in stack:
                return ""
            rendered = str(value)
            if rendered.startswith("&") and len(rendered) > 1:
                return self._render_reference(rendered[1:], values, stack | {normalized})
            return self._render_text(rendered, values, stack | {normalized})
        return str(value)

    def _resolve(self, token: str, values: Mapping[str, Any]) -> Any:
        normalized = token.strip()
        if normalized in values:
            return values[normalized]
        if normalized in self.custom:
            return self.custom[normalized]
        if normalized in DEFAULT_MESSAGES:
            return DEFAULT_MESSAGES[normalized]
        current: Any = values
        for part in normalized.split("."):
            if isinstance(current, Mapping):
                current = current.get(part)
            else:
                current = getattr(current, part, None)
            if current is None:
                break
        return current

    def _render_conditional(
        self,
        method: str,
        parameter: str,
        values: dict[str, Any],
        stack: set[str],
    ) -> str:
        field, separator, choices_text = parameter.partition("?")
        if not separator:
            return ""
        current = self._resolve(field, values)
        choices = self._split_top_level(choices_text, "&")
        selected: str | None = None
        fallback: str | None = None
        numeric_current: float | None = None
        try:
            numeric_current = float(current)
        except (TypeError, ValueError):
            pass
        best_threshold: float | None = None
        for choice in choices:
            name, equals, value = choice.partition("=")
            if not equals:
                continue
            if name == "else":
                fallback = value
                continue
            current_text = "1" if current is True else "0" if current is False else str(current)
            if method == "case":
                if current_text == name:
                    selected = value
                    break
            elif numeric_current is not None:
                try:
                    threshold = float(name)
                except ValueError:
                    continue
                if numeric_current >= threshold and (best_threshold is None or threshold > best_threshold):
                    best_threshold = threshold
                    selected = value
        return self._render_text(selected if selected is not None else (fallback or ""), values, stack)

    def _render_variable(self, parameter: str, values: dict[str, Any], stack: set[str]) -> str:
        assignments = self._split_top_level(parameter, "&")
        output: list[str] = []
        for assignment in assignments:
            question = assignment.find("?")
            equals = assignment.find("=")
            if question >= 0 and (equals < 0 or question < equals):
                name, separator, value = assignment.partition("?")
            else:
                name, separator, value = assignment.partition("=")
            if not separator:
                output.append(self._render_reference(assignment, values, stack))
                continue
            rendered = self._render_text(value, values, stack)
            values[name.strip()] = rendered
            if separator == "?":
                output.append(rendered)
        return "".join(output)

    @classmethod
    def _split_top_level(cls, text: str, delimiter: str) -> list[str]:
        values: list[str] = []
        depth = 0
        start = 0
        for position, character in enumerate(text):
            if character == "{":
                depth += 1
            elif character == "}":
                depth = max(0, depth - 1)
            elif character == delimiter and depth == 0:
                values.append(text[start:position])
                start = position + 1
        values.append(text[start:])
        return values

    def _randint(self, lower: int, upper: int) -> int:
        if lower > upper:
            lower, upper = upper, lower
        if self._random_int is not None:
            return self._random_int(lower, upper)
        import random

        return random.randint(lower, upper)
