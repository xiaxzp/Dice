import unittest

from trpg_dice import (
    ActorRef,
    CheckResult,
    DiceTermResult,
    MessageContext,
    MessageSource,
    RollRequest,
    RollResponse,
    RollResult,
)


class ModelsTest(unittest.TestCase):
    def test_actor_ref_uses_string_ids_and_stable_keys(self):
        actor = ActorRef("qq", "10000000000000000001")
        self.assertEqual(actor.key, "qq:10000000000000000001")
        self.assertEqual(ActorRef.from_dict(actor.to_dict()), actor)

    def test_source_key_keeps_group_and_channel_separate(self):
        group = MessageSource("qq", "group", "12")
        channel = MessageSource("qq", "channel", "12", "34")
        self.assertNotEqual(group.key, channel.key)
        self.assertEqual(MessageSource.from_dict(channel.to_dict()), channel)

    def test_source_key_escapes_delimiters(self):
        source = MessageSource("platform:name", "group", "source:id")
        self.assertEqual(source.key, "platform%3Aname:group:source%3Aid")

    def test_context_requires_matching_platform(self):
        with self.assertRaises(ValueError):
            MessageContext(ActorRef("qq", "1"), MessageSource("discord", "dm", "1"))

    def test_result_models_serialize_nested_data(self):
        term = DiceTermResult(
            notation="B1",
            kind="bonus",
            subtotal=26,
            rolls=(56,),
            kept=(26,),
            base_roll=56,
            extra_tens=(2,),
            count=1,
            sides=100,
        )
        result = RollResult("b", "B1", 26, (term,))
        context = MessageContext(
            ActorRef("qq", "1"), MessageSource("qq", "private", "1")
        )
        response = RollResponse(
            RollRequest(context, "b", reason="检定"), "调查员", "1", "卡片", result
        )
        value = response.to_dict()
        self.assertEqual(value["result"]["terms"][0]["extra_tens"], [2])
        self.assertEqual(value["reason"], "检定")

    def test_check_result_success_property(self):
        result = RollResult("d100", "1d100", 1, ())
        self.assertTrue(CheckResult(50, result, "critical", 0).success)
        self.assertFalse(CheckResult(50, result, "fumble", 0).success)


if __name__ == "__main__":
    unittest.main()
