import asyncio
import json
import re
import runpy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from maibot_plugin.adapter import DICE_COMMAND_PATTERN, DiceCommandAdapter
from trpg_dice import UnknownCommandError


class MaiBotAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.adapter = DiceCommandAdapter(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_maibot_manifest_and_entrypoint_are_at_core_root(self):
        root = Path(__file__).parents[1]
        manifest = json.loads((root / "_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "com.dice-developer.trpg-dice")
        self.assertTrue((root / "plugin.py").is_file())

    def test_plugin_config_contains_sdk_required_version_section(self):
        try:
            from maibot_plugin.plugin import DicePlugin
        except ModuleNotFoundError as error:
            if error.name == "maibot_sdk":
                self.skipTest("maibot-plugin-sdk is only available in the MaiBot environment")
            raise

        config = DicePlugin.build_default_config()
        self.assertEqual(config["plugin"]["config_version"], "2.0.0")

    def test_plugin_declares_a_maibot_command_component(self):
        try:
            from maibot_plugin.plugin import DicePlugin
        except ModuleNotFoundError as error:
            if error.name == "maibot_sdk":
                self.skipTest("maibot-plugin-sdk is only available in the MaiBot environment")
            raise

        info = getattr(DicePlugin.handle_command, "__maibot_component_info__")
        self.assertEqual(info.name, "dice")
        self.assertEqual(info.command_pattern, DICE_COMMAND_PATTERN)
        pattern = re.compile(info.command_pattern)
        self.assertIsNotNone(pattern.search(".r 1"))
        self.assertIsNotNone(pattern.search(".r2#d6"))
        self.assertIsNotNone(pattern.search(".rc3#50"))
        self.assertIsNotNone(pattern.search("!!rc luck"))
        self.assertIsNone(pattern.search("普通消息"))
        self.assertIsNone(pattern.search("？！"))

    def test_command_pattern_only_claims_dice_commands(self):
        pattern = re.compile(DICE_COMMAND_PATTERN)
        for text in (
            ".r 1", ".r3#b hh", ".r2#d6", ".rc3#50", ".rcb2 50", ".rcp2 50",
            ".rb", ".rp", "!!rc luck", "/roll d20", "。RC 幸运", ".ri2DK boss",
            ".coc6d", ".coc7s3", ".st射击40斗殴50", ".st name50",
            ".str strRollDice text", ".rc困难幸运", ".ak#title", ".ak+one|two",
            ".r 1d0", ".rc", ".sc", ".help", ".pc list", ".deck show",
            ".bot on", ".bot off",
            ".ob join", ".set 20", ".setcoc 2", ".name en 2", ".nn 角色", ".nnn jp",
            ".dnd", ".drawh roles", ".game rou show", ".rules dnd", ".rule set dnd",
            ".log new session", ".ti", ".li", ".en hp 10", ".init", ".w 2a8",
            ".ww 敏捷", ".me 做了个动作", ".jrrp", ".welcome 欢迎",
        ):
            with self.subTest(text=text):
                self.assertIsNotNone(pattern.search(text))
        for text in (
            ".hello", "/hello world", ".unknown", ".random", ".restart",
            ".status", ".statistics", ".cocoon", ".drawings", ".read", ".search",
            ".reply off", ".admin", ".cloud", ".send message",
            ".group state", ".rdc", ".rdx", ".rsr", ".rbh", "？！", "普通消息",
        ):
            with self.subTest(text=text):
                self.assertIsNone(pattern.search(text))
                selected = next(
                    (name for name, matcher in (
                        ("dice", pattern), ("other", re.compile(re.escape(text))),
                    ) if matcher.search(text)),
                    None,
                )
                self.assertEqual(selected, "other")

    def test_plugin_does_not_send_or_intercept_unclaimed_commands(self):
        try:
            from maibot_plugin.plugin import DicePlugin
        except ModuleNotFoundError as error:
            if error.name == "maibot_sdk":
                self.skipTest("maibot-plugin-sdk is only available in the MaiBot environment")
            raise

        plugin = DicePlugin()
        plugin.set_plugin_config(DicePlugin.build_default_config())
        sender = AsyncMock()
        plugin._set_context(SimpleNamespace(logger=Mock(), send=SimpleNamespace(text=sender)))
        plugin._adapter = self.adapter
        for text in (".hello", ".random", ".status"):
            with self.subTest(text=text):
                result = asyncio.run(plugin.handle_command(message=self.message(text)))
                self.assertEqual(result, (False, "", 0))
        sender.assert_not_awaited()

        result = asyncio.run(plugin.handle_command(message=self.message(".r 1d0")))
        self.assertTrue(result[0])
        self.assertEqual(result[2], 1)
        self.assertIn("骰子指令错误", result[1])
        sender.assert_awaited_once()

    def test_target_config_defaults_to_enabled(self):
        config_path = Path(__file__).parents[1] / "config.toml"
        if not config_path.exists():
            self.skipTest("MaiBot runtime config is outside the source package")
        self.assertIn("enabled = true", config_path.read_text(encoding="utf-8"))

    def test_root_adapter_is_available_without_installing_core_package(self):
        root = Path(__file__).parents[1]
        namespace = runpy.run_path(str(root / "adapter.py"))
        self.assertIn("DiceCommandAdapter", namespace)

    @staticmethod
    def message(text, *, group=True):
        return {
            "platform": "qq",
            "session_id": "qq-group-42" if group else "qq-private-7",
            "processed_plain_text": text,
            "message_info": {
                "user_info": {
                    "user_id": "7",
                    "user_nickname": "测试用户",
                    "user_cardname": "群名片",
                },
                "group_info": {"group_id": "42", "group_name": "测试群"} if group else None,
            },
        }

    def test_group_command_is_routed_and_intercepted(self):
        result = self.adapter.dispatch(self.message(".r 1"))
        self.assertTrue(result.handled)
        self.assertEqual(result.stream_id, "qq-group-42")
        self.assertIn("群名片掷骰:", result.reply)
        self.assertEqual(result.response.command, "r")

    def test_pre_process_payload_reads_text_segments_before_text_processing(self):
        message = self.message("")
        message.pop("processed_plain_text")
        message["raw_message"] = [{"type": "text", "data": ".r 1"}]
        result = self.adapter.dispatch(message)
        self.assertTrue(result.handled)
        self.assertEqual(result.response.command, "r")

    def test_private_command_uses_private_source(self):
        result = self.adapter.dispatch(self.message("。st name50", group=False))
        self.assertTrue(result.handled)
        self.assertIn("录入", result.reply)

        follow_up = self.adapter.dispatch(self.message(".st show name", group=False))
        self.assertIn("50", follow_up.reply)

    def test_non_command_and_non_qq_messages_are_ignored(self):
        self.assertFalse(self.adapter.dispatch(self.message("2d6")).handled)
        discord = self.message(".r 1")
        discord["platform"] = "discord"
        self.assertFalse(self.adapter.dispatch(discord).handled)

    def test_unknown_and_platform_commands_are_ignored_without_side_effects(self):
        for text in (".hello", "/hello", ".random", ".status", ".rdc"):
            with self.subTest(text=text):
                result = self.adapter.dispatch(self.message(text))
                self.assertFalse(result.handled)
                self.assertEqual(result.reply, "")
                self.assertIsNone(result.response)
        self.assertEqual(list(Path(self.temp_dir.name).rglob("*.json")), [])

    def test_bot_on_and_off_toggle_group_dice_processing(self):
        disabled = self.adapter.dispatch(self.message(".bot off"))
        self.assertTrue(disabled.handled)
        self.assertEqual(disabled.response.result, {"enabled": False, "changed": True})
        self.assertFalse(self.adapter.dispatch(self.message(".r 1")).handled)

        already_disabled = self.adapter.dispatch(self.message(".bot off"))
        self.assertTrue(already_disabled.handled)
        self.assertEqual(already_disabled.response.result["changed"], False)

        enabled = self.adapter.dispatch(self.message(".bot on"))
        self.assertTrue(enabled.handled)
        self.assertEqual(enabled.response.result, {"enabled": True, "changed": True})
        self.assertTrue(self.adapter.dispatch(self.message(".r 1")).handled)

    def test_bot_state_persists_and_is_scoped_to_groups(self):
        self.assertTrue(self.adapter.dispatch(self.message(".bot off")).handled)
        replacement = DiceCommandAdapter(self.temp_dir.name)
        self.assertFalse(replacement.dispatch(self.message(".r 1")).handled)
        other_group = self.message(".r 1")
        other_group["session_id"] = "qq-group-99"
        other_group["message_info"]["group_info"]["group_id"] = "99"
        self.assertTrue(replacement.dispatch(other_group).handled)

    def test_bot_is_not_available_in_private_chat(self):
        result = self.adapter.dispatch(self.message(".bot off", group=False))
        self.assertTrue(result.handled)
        self.assertIn("仅支持群聊", result.reply)

    def test_bot_replies_use_custom_message_templates(self):
        self.adapter.router.messages.set("strBotOff", "custom off {source}")
        result = self.adapter.dispatch(self.message(".bot off"))
        self.assertEqual(result.reply, "custom off 42")

    def test_unknown_router_command_is_not_reported_as_a_dice_error(self):
        with patch.object(self.adapter.router, "execute", side_effect=UnknownCommandError("unknown")):
            result = self.adapter.dispatch(self.message(".r 1"))
        self.assertFalse(result.handled)
        self.assertEqual(result.reply, "")

    def test_invalid_dice_arguments_are_still_handled(self):
        result = self.adapter.dispatch(self.message(".r 1d0"))
        self.assertTrue(result.handled)
        self.assertIn("骰子指令错误", result.reply)

    def test_configured_slash_prefix_is_normalized_for_core_router(self):
        adapter = DiceCommandAdapter(self.temp_dir.name, prefixes=("/",))
        result = adapter.dispatch(self.message("/r 1"))
        self.assertTrue(result.handled)
        self.assertEqual(result.response.command, "r")

    def test_custom_symbol_prefix_keeps_command_ownership_check(self):
        adapter = DiceCommandAdapter(self.temp_dir.name, prefixes=("#",))
        self.assertTrue(adapter.dispatch(self.message("#r3#b hh")).handled)
        self.assertFalse(adapter.dispatch(self.message("#hello")).handled)

    def test_handle_sends_only_for_a_hit(self):
        sent = []

        async def send_text(text, stream_id):
            sent.append((text, stream_id))

        asyncio.run(self.adapter.handle(self.message("!r 1"), send_text=send_text))
        asyncio.run(self.adapter.handle(self.message("普通消息"), send_text=send_text))
        asyncio.run(self.adapter.handle(self.message(".hello"), send_text=send_text))
        asyncio.run(self.adapter.handle(self.message(".status"), send_text=send_text))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1], "qq-group-42")


if __name__ == "__main__":
    unittest.main()
