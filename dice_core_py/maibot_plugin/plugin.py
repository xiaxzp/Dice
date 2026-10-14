from __future__ import annotations

from pathlib import Path
from typing import Any

from maibot_sdk import Command, Field, MaiBotPlugin, PluginConfigBase

try:
    from .adapter import DEFAULT_PREFIXES, DICE_COMMAND_PATTERN, DiceCommandAdapter
except ImportError:
    from adapter import DEFAULT_PREFIXES, DICE_COMMAND_PATTERN, DiceCommandAdapter


class PluginSectionConfig(PluginConfigBase):
    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default="2.0.0", description="配置版本")


class DicePluginConfig(PluginConfigBase):
    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    enabled: bool = Field(default=True, description="是否启用 MaiBot 骰子指令")
    qq_only: bool = Field(default=True, description="是否只处理 QQ 消息")
    prefixes: list[str] = Field(
        default=list(DEFAULT_PREFIXES),
        description="触发骰子指令的消息前缀，例如 .、。或！",
    )


class DicePlugin(MaiBotPlugin):
    config_model = DicePluginConfig

    def __init__(self) -> None:
        super().__init__()
        self._adapter: DiceCommandAdapter | None = None

    async def on_load(self) -> None:
        self._build_adapter()
        self.ctx.logger.info(
            "[TRPG Dice] 插件已加载: enabled=%s, plugin_enabled=%s, qq_only=%s, prefixes=%r, data_dir=%s",
            self.config.enabled,
            self.config.plugin.enabled,
            self.config.qq_only,
            self.config.prefixes,
            self.ctx.paths.data_dir,
        )

    async def on_unload(self) -> None:
        self._adapter = None

    async def on_config_update(
        self,
        scope: str,
        config_data: dict[str, Any],
        version: str,
    ) -> None:
        self.ctx.logger.info(
            "[TRPG Dice] 配置更新: scope=%s, version=%s, config=%r",
            scope,
            version,
            config_data,
        )
        self._build_adapter()

    @Command(
        "dice",
        description="处理 .、/、。等前缀的 TRPG 骰子指令",
        pattern=DICE_COMMAND_PATTERN,
    )
    async def handle_command(self, **kwargs: Any) -> tuple[bool, str, int]:
        message = kwargs.get("message")
        text = self._message_text(message, kwargs)
        self.ctx.logger.info(
            "[TRPG Dice] Command 已进入: text=%r, stream_id=%r, platform=%r, user_id=%r, group_id=%r, matched_groups=%r",
            text[:300],
            kwargs.get("stream_id") or self._message_field(message, "session_id"),
            kwargs.get("platform") or self._message_field(message, "platform"),
            kwargs.get("user_id") or self._nested_message_field(message, "user_info", "user_id"),
            kwargs.get("group_id") or self._nested_message_field(message, "group_info", "group_id"),
            kwargs.get("matched_groups"),
        )
        if not self.config.plugin.enabled or not self.config.enabled:
            self.ctx.logger.warning(
                "[TRPG Dice] Command 被配置禁用: enabled=%s, plugin_enabled=%s",
                self.config.enabled,
                self.config.plugin.enabled,
            )
            return False, "", 0
        if self._adapter is None:
            self.ctx.logger.warning("[TRPG Dice] 适配器为空，正在重新构建")
            self._build_adapter()
        if self._adapter is None:
            self.ctx.logger.error("[TRPG Dice] 适配器构建失败")
            return False, "", 0

        dispatch = self._adapter.dispatch(
            message,
            plain_text=kwargs.get("plain_text"),
            text=kwargs.get("text"),
            stream_id=kwargs.get("stream_id"),
            chat_id=kwargs.get("chat_id"),
            platform=kwargs.get("platform"),
            user_id=kwargs.get("user_id"),
            user_nickname=kwargs.get("user_nickname"),
            user_cardname=kwargs.get("user_cardname"),
            group_id=kwargs.get("group_id"),
            group_name=kwargs.get("group_name"),
        )
        self.ctx.logger.info(
            "[TRPG Dice] 适配器结果: handled=%s, stream_id=%r, reply=%r, command=%r",
            dispatch.handled,
            dispatch.stream_id,
            dispatch.reply[:300],
            dispatch.response.command if dispatch.response else None,
        )
        if not dispatch.handled:
            self.ctx.logger.warning(
                "[TRPG Dice] 消息未被骰子适配器处理: text=%r, configured_prefixes=%r",
                text[:300],
                self.config.prefixes,
            )
            return False, "", 0

        try:
            if dispatch.stream_id:
                self.ctx.logger.info(
                    "[TRPG Dice] 准备发送回复: stream_id=%r, length=%d",
                    dispatch.stream_id,
                    len(dispatch.reply),
                )
                await self.ctx.send.text(
                    dispatch.reply,
                    dispatch.stream_id,
                    set_reply=True,
                    reply_message=message,
                )
                self.ctx.logger.info("[TRPG Dice] 回复发送成功: stream_id=%r", dispatch.stream_id)
            else:
                self.ctx.logger.error("[TRPG Dice] 没有可用 stream_id，无法发送回复")
        except Exception:
            self.ctx.logger.exception("[TRPG Dice] 发送骰子结果失败")
            return False, "骰子结果发送失败", 1
        return True, dispatch.reply, 1

    def _build_adapter(self) -> None:
        config = self.config
        data_dir = Path(self.ctx.paths.data_dir)
        platforms = ("qq",) if config.qq_only else None
        self._adapter = DiceCommandAdapter(
            data_dir,
            prefixes=config.prefixes,
            platforms=platforms,
        )
        self.ctx.logger.info(
            "[TRPG Dice] 适配器已构建: platforms=%r, prefixes=%r, data_dir=%s",
            platforms,
            config.prefixes,
            data_dir,
        )

    @staticmethod
    def _message_field(message: Any, field: str) -> Any:
        if isinstance(message, dict):
            return message.get(field)
        return getattr(message, field, None)

    @classmethod
    def _nested_message_field(cls, message: Any, parent: str, field: str) -> Any:
        value = cls._message_field(message, parent)
        if isinstance(value, dict):
            return value.get(field)
        return getattr(value, field, None) if value is not None else None

    @classmethod
    def _message_text(cls, message: Any, kwargs: dict[str, Any]) -> str:
        for value in (
            cls._message_field(message, "processed_plain_text"),
            kwargs.get("text"),
            kwargs.get("raw_message"),
        ):
            if value:
                return str(value)
        raw_message = cls._message_field(message, "raw_message")
        components = cls._message_field(raw_message, "components")
        if isinstance(components, list):
            return "".join(
                str(cls._message_field(component, "data") or "")
                for component in components
                if cls._message_field(component, "type") == "text"
            )
        return ""


def create_plugin() -> DicePlugin:
    return DicePlugin()
