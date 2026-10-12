import tempfile
import unittest

from trpg_dice import (
    ActorRef,
    CommandRouter,
    DEFAULT_MESSAGES,
    DiceEngine,
    DiceRoller,
    IdentityServices,
    MessageContext,
    MessageCatalog,
    MessageSource,
    ProfileRepository,
    SequenceRandomSource,
)


class MessageCatalogTest(unittest.TestCase):
    def test_default_references_and_nested_methods(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = MessageCatalog(root, random_int=lambda lower, upper: lower)
            self.assertEqual(catalog.render("strSelfCall"), "")
            catalog.set("x", "{sample:a|b}")
            self.assertEqual(catalog.render("x"), "a")
            catalog.set("x", "{case:key?yes=Y&else=N}")
            self.assertEqual(catalog.render("x", {"key": "yes"}), "Y")
            catalog.set("x", "{grade:n?0=zero&2=two&else=other}")
            self.assertEqual(catalog.render("x", {"n": 3}), "two")
            catalog.set("x", "{var:value?ok}{value}")
            self.assertEqual(catalog.render("x"), "okok")

    def test_custom_messages_persist_and_reset(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = MessageCatalog(root)
            catalog.set("strRollDice", "custom {pc} {res}")
            self.assertEqual(MessageCatalog(root).get("strRollDice"), "custom {pc} {res}")
            self.assertTrue(catalog.reset("strRollDice"))
            self.assertEqual(catalog.get("strRollDice"), DEFAULT_MESSAGES["strRollDice"])


class CommandMessageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        identities = IdentityServices(ProfileRepository(self.temp_dir.name))
        self.router = CommandRouter(
            DiceEngine(identities, DiceRoller(SequenceRandomSource([1, 2, 3, 4, 5, 6] * 20)))
        )
        self.context = MessageContext(
            ActorRef("qq", "1"),
            MessageSource("qq", "group", "2"),
            account_nickname="用户",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_str_customizes_roll_and_survives_new_router(self):
        self.router.execute(self.context, ".str strRollDice 前缀:{pc}|{res}")
        response = self.router.execute(self.context, ".r d6")
        self.assertTrue(response.rendered.startswith("前缀:用户|"))
        self.assertEqual(
            CommandRouter(
                DiceEngine(self.router.identities, self.router.roller)
            ).messages.get("strRollDice"),
            "前缀:{pc}|{res}",
        )

    def test_repeated_roll_uses_multi_message(self):
        response = self.router.execute(self.context, ".r2#d6")
        self.assertIn("掷骰2次", response.rendered)
        self.assertIn("d6", response.rendered)

    def test_hidden_roll_keeps_private_render(self):
        response = self.router.execute(self.context, ".rh d6")
        self.assertIn("暗骰", response.rendered)
        self.assertIn("private_rendered", response.metadata)


if __name__ == "__main__":
    unittest.main()
