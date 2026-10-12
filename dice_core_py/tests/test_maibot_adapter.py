import asyncio
import json
import re
import runpy
import tempfile
import unittest
from pathlib import Path

from maibot_plugin.adapter import DiceCommandAdapter


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
        self.assertEqual(info.command_pattern, r"^[^\w\s]+(?=\S*\w)\S+(?:\s.*)?$")
        pattern = re.compile(info.command_pattern)
        self.assertIsNotNone(pattern.search(".r 1"))
        self.assertIsNotNone(pattern.search(".r2#d6"))
        self.assertIsNotNone(pattern.search(".rc3#50"))
        self.assertIsNotNone(pattern.search("!!rc luck"))
        self.assertIsNone(pattern.search("普通消息"))
        self.assertIsNone(pattern.search("？！"))

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

    def test_configured_slash_prefix_is_normalized_for_core_router(self):
        adapter = DiceCommandAdapter(self.temp_dir.name, prefixes=("/",))
        result = adapter.dispatch(self.message("/r 1"))
        self.assertTrue(result.handled)
        self.assertEqual(result.response.command, "r")

    def test_handle_sends_only_for_a_hit(self):
        sent = []

        async def send_text(text, stream_id):
            sent.append((text, stream_id))

        asyncio.run(self.adapter.handle(self.message("!r 1"), send_text=send_text))
        asyncio.run(self.adapter.handle(self.message("普通消息"), send_text=send_text))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1], "qq-group-42")


if __name__ == "__main__":
    unittest.main()
