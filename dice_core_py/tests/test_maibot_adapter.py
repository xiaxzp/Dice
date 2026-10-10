import asyncio
import tempfile
import unittest

from maibot_plugin.adapter import DiceCommandAdapter


class MaiBotAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.adapter = DiceCommandAdapter(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

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
        self.assertIn("群名片:", result.reply)
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
        self.assertIn("name", result.reply)

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
