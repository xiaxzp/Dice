import tempfile
import unittest

from trpg_dice import (
    ActorRef,
    DiceEngine,
    DiceRoller,
    IdentityServices,
    MessageContext,
    MessageSource,
    ProfileRepository,
    RollRequest,
    SequenceRandomSource,
)


class EngineTest(unittest.TestCase):
    def test_engine_uses_card_default_and_identity_inputs(self):
        with tempfile.TemporaryDirectory() as root:
            identities = IdentityServices(ProfileRepository(root))
            actor = ActorRef("qq", "1")
            source = MessageSource("qq", "group", "2")
            identities.nicknames.set(actor, "玩家", source)
            card = identities.characters.create(
                actor, "角色", attributes={"__DefaultDice": "d6"}
            )
            identities.characters.bind(actor, source, card.card_id)
            response = DiceEngine(
                identities, DiceRoller(SequenceRandomSource([4]))
            ).roll(RollRequest(MessageContext(actor, source)))
            self.assertEqual(response.display_name, "玩家")
            self.assertEqual(response.card_name, "角色")
            self.assertEqual(response.result.total, 4)

    def test_explicit_expression_overrides_card_default(self):
        with tempfile.TemporaryDirectory() as root:
            identities = IdentityServices(ProfileRepository(root))
            actor = ActorRef("qq", "1")
            source = MessageSource("qq", "private", "1")
            card = identities.characters.create(
                actor, "角色", attributes={"__DefaultDice": "d6"}
            )
            identities.characters.bind(actor, source, card.card_id)
            response = DiceEngine(
                identities, DiceRoller(SequenceRandomSource([2, 3]))
            ).roll(RollRequest(MessageContext(actor, source), "2d6"))
            self.assertEqual(response.result.total, 5)

    def test_engine_returns_structured_data_without_sending_messages(self):
        with tempfile.TemporaryDirectory() as root:
            identities = IdentityServices(ProfileRepository(root))
            context = MessageContext(
                ActorRef("discord", "1"), MessageSource("discord", "dm", "1")
            )
            response = DiceEngine(
                identities, DiceRoller(SequenceRandomSource([1]))
            ).roll(RollRequest(context, "d20", reason="测试"))
            self.assertEqual(response.to_dict()["reason"], "测试")
            self.assertNotIn("reply", response.to_dict())


if __name__ == "__main__":
    unittest.main()
