import tempfile
import unittest
from pathlib import Path

from trpg_dice import (
    ActorRef,
    CharacterService,
    ConflictError,
    DiceEngine,
    IdentityServices,
    MessageContext,
    MessageSource,
    NicknameService,
    ProfileRepository,
    RollRequest,
    SeededRandomSource,
    DiceRoller,
    StorageError,
)


class IdentityAndStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = ProfileRepository(self.temp_dir.name)
        self.characters = CharacterService(repository)
        self.nicknames = NicknameService(repository)
        self.identities = IdentityServices(repository)
        self.actor = ActorRef("qq", "10000000000000000001")
        self.group = MessageSource("qq", "group", "42")
        self.channel = MessageSource("qq", "channel", "42", "7")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_nickname_and_card_binding_are_source_specific(self):
        self.nicknames.set(self.actor, "全局名")
        self.nicknames.set(self.actor, "群内名", self.group)
        card = self.characters.create(self.actor, "调查员", attributes={"__DefaultDice": "d20"})
        self.characters.bind(self.actor, self.group, card.card_id)

        group_context = MessageContext(
            self.actor,
            self.group,
            account_nickname="账号名",
            source_nickname="群名片",
        )
        channel_context = MessageContext(
            self.actor,
            self.channel,
            account_nickname="账号名",
            source_nickname="频道昵称",
        )
        self.assertEqual(self.nicknames.resolve(group_context), "群内名")
        self.assertEqual(self.nicknames.resolve(channel_context), "全局名")
        self.assertEqual(self.characters.resolve(group_context).card_id, card.card_id)
        self.assertIsNone(self.characters.resolve(channel_context))

    def test_engine_uses_card_default_expression_and_returns_data(self):
        card = self.characters.create(
            self.actor, "角色", attributes={"__DefaultDice": "d6"}
        )
        self.characters.bind(self.actor, self.group, card.card_id)
        context = MessageContext(self.actor, self.group, account_nickname="角色玩家")
        response = DiceEngine(
            self.identities,
            DiceRoller(SeededRandomSource(1)),
        ).roll(RollRequest(context))
        self.assertEqual(response.card_name, "角色")
        self.assertEqual(response.result.normalized_expression, "1d6")

    def test_duplicate_names_and_delete_cleanup(self):
        card = self.characters.create(self.actor, "角色")
        with self.assertRaises(ConflictError):
            self.characters.create(self.actor, "角色")
        self.characters.bind(self.actor, self.group, card.card_id)
        self.characters.delete(self.actor, card.card_id)
        context = MessageContext(self.actor, self.group)
        self.assertIsNone(self.characters.resolve(context))

    def test_json_is_utf8_and_corruption_is_reported(self):
        card = self.characters.create(self.actor, "中文角色", attributes={"力量": 60})
        loaded = self.characters.get(self.actor, card.card_id)
        self.assertEqual(loaded.attributes["力量"], 60)
        profile_path = Path(self.temp_dir.name) / "profiles"
        json_files = list(profile_path.glob("*.json"))
        self.assertEqual(len(json_files), 1)
        raw = json_files[0].read_text(encoding="utf-8")
        self.assertIn("schema_version", raw)
        json_files[0].write_text("{broken", encoding="utf-8")
        with self.assertRaises(StorageError):
            self.characters.list(self.actor)

    def test_platform_and_source_keys_do_not_collide(self):
        other_actor = ActorRef("discord", self.actor.user_id)
        self.characters.create(self.actor, "QQ角色")
        self.characters.create(other_actor, "Discord角色")
        self.assertEqual(self.characters.list(self.actor)[0].name, "QQ角色")
        self.assertEqual(self.characters.list(other_actor)[0].name, "Discord角色")


if __name__ == "__main__":
    unittest.main()
