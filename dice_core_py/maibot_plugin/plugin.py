from __future__ import annotations

from pathlib import Path
from typing import Any

from maibot_sdk import EventHandler, Field, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import EventType

try:
    from .adapter import DEFAULT_PREFIXES, DiceCommandAdapter
except ImportError:
    from adapter import DEFAULT_PREFIXES, DiceCommandAdapter


class DicePluginConfig(PluginConfigBase):
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
        self.ctx.logger.info("TRPG Dice MaiBot 适配器已加载")

    async def on_unload(self) -> None:
        self._adapter = None

    async def on_config_update(
        self,
        scope: str,
        config_data: dict[str, Any],
        version: str,
    ) -> None:
        del scope, config_data, version
        self._build_adapter()

    @EventHandler(
        "dice_command_receiver",
        description="拦截 .、。等前缀的骰子指令并回复结果",
        event_type=EventType.ON_MESSAGE_PRE_PROCESS,
        intercept_message=True,
        weight=1000,
    )
    async def handle_message(self, **kwargs: Any) -> dict[str, Any] | None:
        if not self.config.enabled:
            return None
        if self._adapter is None:
            self._build_adapter()
        if self._adapter is None:
            return None

        dispatch = self._adapter.dispatch(
            kwargs.get("message"),
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
        if not dispatch.handled:
            return None

        try:
            if dispatch.stream_id:
                await self.ctx.send.text(dispatch.reply, dispatch.stream_id)
        except Exception:
            self.ctx.logger.exception("发送骰子结果失败，仍拦截原始指令")
        return {
            "blocked": True,
            "custom_result": {
                "command": dispatch.response.command if dispatch.response else None,
                "stream_id": dispatch.stream_id,
            },
        }

    def _build_adapter(self) -> None:
        config = self.config
        data_dir = Path(self.ctx.paths.data_dir)
        platforms = ("qq",) if config.qq_only else None
        self._adapter = DiceCommandAdapter(
            data_dir,
            prefixes=config.prefixes,
            platforms=platforms,
        )


def create_plugin() -> DicePlugin:
    return DicePlugin()
