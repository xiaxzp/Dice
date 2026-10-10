import tempfile
import unittest

from trpg_dice import (
    ActorRef,
    CharacterService,
    ConflictError,
    IdentityServices,
    IdentityError,
    MessageContext,
    MessageSource,
    NicknameService,
    NotFoundError,
    ProfileRepository,
)


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = ProfileRepository(self.temp_dir.name)
        self.characters = CharacterService(repository)
        self.nicknames = NicknameService(repository)
        self.actor = ActorRef("qq", "10000000000000000001")
        self.group = MessageSource("qq", "group", "42")
        self.channel = MessageSource("qq", "channel", "42", "7")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_nickname_resolution_priority_and_removal(self):
        context = MessageContext(self.actor, self.group, "账号昵称", "来源昵称")
        self.assertEqual(self.nicknames.resolve(context), "来源昵称")
        self.nicknames.set(self.actor, "全局昵称")
        self.assertEqual(self.nicknames.resolve(context), "全局昵称")
        self.nicknames.set(self.actor, "群昵称", self.group)
        self.assertEqual(self.nicknames.resolve(context), "群昵称")
        self.assertTrue(self.nicknames.remove(self.actor, self.group))
        self.assertFalse(self.nicknames.remove(self.actor, self.group))

    def test_nickname_falls_back_to_opaque_actor_id(self):
        context = MessageContext(self.actor, self.group)
        self.assertEqual(self.nicknames.resolve(context), "陌生人(10000000000000000001)")

    def test_character_crud_update_rename_and_listing(self):
        card = self.characters.create(self.actor, "调查员", system="COC7", attributes={"力量": 60})
        updated = self.characters.update(self.actor, card.card_id, attributes={"力量": 70})
        renamed = self.characters.rename(self.actor, updated.card_id, "新调查员")
        self.assertEqual(renamed.attributes["力量"], 70)
        self.assertEqual(self.characters.get(self.actor, card.card_id).name, "新调查员")
        self.assertEqual(self.characters.list(self.actor)[0].card_id, card.card_id)

    def test_character_conflicts_missing_cards_and_locks(self):
        card = self.characters.create(self.actor, "角色")
        with self.assertRaises(ConflictError):
            self.characters.create(self.actor, "角色")
        with self.assertRaises(NotFoundError):
            self.characters.get(self.actor, "missing")
        locked = self.characters.update(self.actor, card.card_id, attributes={}, system="generic")
        profile = self.characters.repository.load(self.actor)
        profile.cards[locked.card_id] = type(locked)(
            locked.card_id, locked.name, locked.system, locked.attributes, frozenset({"n", "q"}), locked.updated_at
        )
        self.characters.repository.save(profile)
        with self.assertRaises(IdentityError):
            self.characters.rename(self.actor, card.card_id, "新名")
        with self.assertRaises(IdentityError):
            self.characters.update(self.actor, card.card_id, attributes={"x": 1})

    def test_source_and_global_character_bindings(self):
        source_card = self.characters.create(self.actor, "来源卡")
        global_card = self.characters.create(self.actor, "全局卡")
        self.characters.bind(self.actor, self.group, source_card.card_id)
        self.characters.bind_global(self.actor, global_card.card_id)
        self.assertEqual(
            self.characters.resolve(MessageContext(self.actor, self.group)).name, "来源卡"
        )
        self.assertEqual(
            self.characters.resolve(MessageContext(self.actor, self.channel)).name, "全局卡"
        )
        self.characters.unbind(self.actor, self.group)
        self.assertEqual(
            self.characters.resolve(MessageContext(self.actor, self.group)).name, "全局卡"
        )

    def test_delete_removes_bindings(self):
        card = self.characters.create(self.actor, "临时卡")
        self.characters.bind(self.actor, self.group, card.card_id)
        self.characters.bind_global(self.actor, card.card_id)
        self.characters.delete(self.actor, card.card_id)
        profile = self.characters.repository.load(self.actor)
        self.assertNotIn(self.group.key, profile.bindings)
        self.assertNotIn("global", profile.bindings)


if __name__ == "__main__":
    unittest.main()
