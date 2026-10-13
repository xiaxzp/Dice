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
    "strObOnAlready": "在本桌{self}未禁用旁观!",
    "strObOffAlready": "在本桌{self}已禁用旁观!",
    "strObList": "本桌{self}的旁观者有:",
    "strObListEmpty": "本桌{self}暂无旁观者",
    "strObListClr": "{self}已清空旁观者√",
    "strNumCannotBeZero": "无意义的数目！莫要消遣于我!",
    "strDeckNotFound": "是说{deck_name}？{self}没听说过的牌堆名呢……",
    "strDeckEmpty": "{self}已经一张也不剩了！",
    "strDeckNew": "{self}已为{nick}自定义新牌堆<{deck_name}>√",
    "strDeckSet": "{nick}已用<{deck_name}>创建{self}的牌堆实例√",
    "strDeckSetRename": "{nick}已用<{deck_cited}>创建{self}的牌堆实例{deck_name}√",
    "strDeckRestEmpty": "牌堆<{deck_name}>已抽空，请使用.deck reset {deck_name}手动重置牌堆",
    "strDeckRestShow": "当前牌堆<{deck_name}>剩余卡牌:{deck_rest}",
    "strDeckRestReset": "{self}已重置牌堆实例<{deck_name}>√",
    "strDeckDelete": "{self}已移除牌堆实例<{deck_name}>√",
    "strDeckListShow": "在{self}处创建的牌堆实例有:{res}",
    "strDeckListClr": "{nick}已清空{self}处牌堆实例√",
    "strDeckListEmpty": "{self}处牌堆实例列表为空！",
    "strDeckNewEmpty": "{self}无法为{nick}新建虚空牌堆×",
    "strDeckListFull": "{self}处牌堆实例已达上限，请先清理无用实例×",
    "strDeckOversize": "{nick}定义的牌太多，{self}装不下啦×",
    "strDeckNameEmpty": "{nick}未指定牌堆名×",
    "strDeckCiteNotFound": "{self}找不到公共牌堆{deck_cited}×",
    "strNameNumTooBig": "想取多少个名字啊!请{nick}输入1-10之间的数字!",
    "strNameNumCannotBeZero": "让{self}取0个名字？请{nick}输入1-10之间的数字!",
    "strSetTooBig": "这面数……让我丢个球啊!请{nick}输入1-9999之间的数字!",
    "strSetCannotBeZero": "默认骰不能为零!请{nick}输入1-9999之间的数字!",
    "strSetDefaultDice": "{self}已将{pc}的默认骰设置为D{default}√",
    "strDefaultCOCShow": "{self}记录默认房规为{rule}",
    "strDefaultCOCShowDefault": "{self}未记录默认房规，使用默认房规{rule}",
    "strDefaultCOCClr": "默认检定房规已清除√",
    "strDefaultCOCNotFound": "默认检定房规不存在×",
    "strDefaultCOCSet": "默认检定房规已设置:",
    "strProp": "{pc}的{attr}为{val}",
    "strPropList": "{nick}的{char}属性列表为：{show}",
    "strPropCleared": "{self}已清空{char}的所有属性√",
    "strPropDeleted": "已删除{pc}的{attr}√",
    "strSetPropSuccess": "{self}已为{pc}录入{cnt}条属性√",
    "strNameSet": "{self}已将{old_nick}改称为{new_nick}√",
    "strNameDel": "{self}已删除{old_nick}在当前窗口的称呼√",
    "strNameClr": "{self}已清空{old_nick}的所有称呼√",
    "strMeOnAlready": "在这里{self}的.me命令没有被禁用!",
    "strMeOffAlready": "在这里{self}的.me命令已经被禁用!",
    "strNameDelEmpty": "{nick}未设置名称,无法删除!",
    "strCharacterCannotBeZero": "人物作成次数不能为零!请输入1-10之间的数字!",
    "strBuildTooMany": "人物作成次数过多!请输入1-10之间的数字!",
    "strCharacterInvalid": "人物作成次数无效!请输入1-10之间的数字!",
    "strRangeEmpty": "{self}没法对着空气数数×",
    "strOutRange": "{nick}定义的数列超出{self}允许范围×",
    "strParaIllegal": "参数非法×",
    "strPermissionDeniedErr": "请让群内管理对{self}发送该指令×",
    "strMEDisabledErr": "管理员已在此群中禁用.me命令!",
    "strPropNotFound": "属性{attr}不存在×",
    "strPcNotExistErr": "{self}无{nick}的角色卡记录，无法删除×",
    "strGMTableShow": "{self}记录的{table_name}列表: {res}",
    "strGMTableClr": "{self}已清除{table_name}表√",
    "strGMTableItemDel": "{self}已移除{table_name}表的项目{table_item}√",
    "strGMTableNotExist": "{self}没有保存{table_name}表×",
    "strGMTableItemNotFound": "{self}没有找到{table_name}表的项目{table_item}×",
    "strGMTableItemEmpty": "请告知{self}待移除的{table_name}列表项目×",
    "strNameTooLongErr": "称呼过长×(最多50字节)",
    "strCOCBuild": "{pc}的调查员作成:{res}",
    "strDNDBuild": "为{pc}的冒险者生成随机六维（降序）:{res}",
    "strPcNewEmptyCard": "已为{nick}新建{type}空白卡「{char}」√",
    "strPcCardSet": "已将{nick}当前角色卡绑定为「{char}」√",
    "strPcCardReset": "已解绑{nick}当前的默认卡√",
    "strPcCardRename": "已将{old_name}重命名为「{new_name}」√",
    "strPcCardDel": "已将角色卡「{char}」删除√",
    "strPcCardCpy": "已将「{char2}」的属性复制到「{char1}」√",
    "strPcClr": "已清空{nick}的角色卡记录√",
    "strPcCardList": "{nick}的角色列表：{show}",
    "strPcCardBuild": "{nick}的「{char}」生成：{show}",
    "strPcCardRedo": "{nick}的「{char}」重新生成：{show}",
    "strPcGroupList": "{nick}的各群角色列表：{show}",
    "strPcStatShow": "{pc}在{self}处的骰点统计:{stat}",
    "strPcStatEmpty": "{pc}在{self}处还没有检定被记录的样子×",
    "strRuleReset": "{self}已重置默认规则√",
    "strRuleSet": "{self}已设置默认规则{rule}√",
    "strRuleErr": "规则数据获取失败,具体信息:\n{err}",
    "strRuleNotFound": "{self}未找到对应的规则词条{item}×",
    "strRulesFormatErr": "格式错误:正确格式为.rules[规则名称:]规则条目 如.rules COC7:力量",
    "strAkForkNew": "{self}已创建分歧\n#{fork}",
    "strAkAdd": "{self}已加入新选项√\n当前分歧:{fork}{li}",
    "strAkAddEmpty": "给完{nick}的选项，就像{self}没看到这句话之前一样×",
    "strAkDel": "{self}已删除指定选项√\n当前分歧:{fork}{li}",
    "strAkOptEmptyErr": "备选项为空×\n{nick}想让{self}编出一个选项吗？",
    "strAkNumErr": "请{nick}选择合法的选项序号×",
    "strAkGet": "#{fork}{li}\n\n{self}的选择：{get}",
    "strAkShow": "{self}的当前分歧:{fork} {li}",
    "strAkClr": "{self}已清除本轮分歧{fork}√",
    "strLogNew": "{self}已新开记录日志「{game.log_name}」√\n请适时用.log off暂停或.log end完成记录",
    "strLogOn": "{self}开始日志记录「{game.log_name}」√\n可使用.log off暂停记录",
    "strLogOnAlready": "{self}正在记录「{game.log_name}」中！",
    "strLogOff": "{self}已暂停日志「{game.log_name}」记录√\n可使用.log on恢复记录",
    "strLogOffAlready": "{self}已经暂停「{game.log_name}」记录！",
    "strLogEnd": "{self}已完成日志记录√\n正在上传日志文件{log_file}",
    "strLogEndEmpty": "{self}已结束「{game.log_name}」记录√\n本次无日志产生",
    "strLogNullErr": "{self}无日志记录或已结束！",
    "strGameNew": "{self}创建新游戏「{game_id}」成功√",
    "strGameOver": "游戏「{game_id}」已终结√",
    "strGameMastered": "{self}已接受{nick}为本桌游戏管理员√",
    "strGameMasterList": "本桌游戏管理员有:\n{items}",
    "strGameMasterDenied": "抱歉，GM权限不能交给{nick}×",
    "strGameJoined": "{self}已接受{nick}的玩家报名√",
    "strGamePlayerAlready": "{nick}已经上桌啦！",
    "strGamePlayerCall": "{items}",
    "strGamePlayerEmpty": "{self}还没看到有玩家上桌哦~",
    "strGameExited": "玩家{nick}已退出游戏√",
    "strGameNotJoined": "嗯？{nick}原来有在桌上吗？",
    "strGameNotMaster": "请{nick}让这桌的GM进行此操作×",
    "strGameVoidHere": "{self}连桌布还没铺上，{nick}就要动桌子么？(请先.game new 新建游戏)",
    "strGameNotExist": "{self}不记得有一桌叫{game_id}的游戏了×",
    "strGameItemSet": "{self}已将本桌游戏的{set_item}设置为{set_val}√",
    "strGameItemShow": "本桌游戏的{set_item}为{set_val}√",
    "strGameItemEmpty": "请{nick}输入待设置的项目×",
    "strGameAreaOpen": "{self}已在此展开「{game_id}」游戏领域√",
    "strGameAreaClosed": "游戏领域关闭，{nick}可用.game open {game_id} 重新展开√",
    "strGameRouletteSet": "{self}已为{face}面骰启用轮盘骰√",
    "strGameRouletteTooBig": "这么大……{nick}丢得完吗？",
    "strGameRouletteHistory": "{self}本轮轮盘骰记录如下:\n{hist}",
    "strGameRouletteEmpty": "{self}并未在本桌用过轮盘骰×",
    "strGameRouletteClear": "{self}已清空桌上轮盘骰√",
    "strGameRouletteReset": "{self}已复原桌上轮盘骰√",
    "strGameOver": "游戏「{game_id}」已终结√",
    "strJrrpOn": "成功在本群中启用JRRP!",
    "strJrrpOff": "成功在本群中禁用JRRP!",
    "strJrrpOnAlready": "在本群中JRRP没有被禁用!",
    "strJrrpOffAlready": "在本群中JRRP没有被启用!",
    "strActionEmpty": "动作不能为空×",
    "strWelcomePrivate": "你在私聊窗口想{self}欢迎谁呢？",
    "strWelcomeMsgClearNotice": "{self}已清除本群的入群欢迎词√",
    "strWelcomeMsgClearErr": "没有设置{self}入群欢迎词，清除失败×",
    "strWelcomeMsgUpdateNotice": "{self}已更新本群的入群欢迎词√",
    "strWelcomeMsgEmpty": "{self}当前未记录入群欢迎词",
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
