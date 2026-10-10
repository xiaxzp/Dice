import tempfile
import unittest

from trpg_dice import (
    ActorRef,
    CommandError,
    CommandRouter,
    DiceEngine,
    DiceRoller,
    IdentityServices,
    MessageContext,
    MessageSource,
    ProfileRepository,
    SeededRandomSource,
    UnknownCommandError,
)


class CommandRouterTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        identities = IdentityServices(ProfileRepository(self.temp_dir.name))
        self.router = CommandRouter(
            DiceEngine(identities, DiceRoller(SeededRandomSource(1234)))
        )
        self.context = MessageContext(
            ActorRef("qq", "1"),
            MessageSource("qq", "group", "2"),
            account_nickname="测试用户",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_command(self, text):
        return self.router.execute(self.context, text)

    def test_r_is_the_general_roll_entry_point(self):
        response = self.run_command(".r 2d6+3 伤害")
        self.assertEqual(response.command, "r")
        self.assertEqual(response.metadata["reason"], "伤害")
        self.assertEqual(response.result.request.reason, "伤害")
        self.assertIn("测试用户:", response.rendered)

    def test_r_aliases_hidden_short_bonus_penalty_and_repeat(self):
        self.assertEqual(self.run_command("。rh d20").metadata["hidden"], True)
        self.assertEqual(self.run_command(".rs d20").metadata["short"], True)
        self.assertEqual(
            self.run_command(".rb").result.result.normalized_expression, "B1"
        )
        self.assertEqual(
            self.run_command(".rp").result.result.normalized_expression, "P1"
        )
        self.assertEqual(self.run_command(".rb2").result.result.terms[0].kind, "bonus")
        self.assertEqual(self.run_command(".rp2").result.result.terms[0].kind, "penalty")
        repeated = self.run_command(".r2#d6")
        self.assertEqual(repeated.metadata["repeat"], 2)
        self.assertEqual(len(repeated.result), 2)

    def test_rc_ra_and_rcp_route_to_check_tools(self):
        normal = self.run_command(".rc 50")
        bonus = self.run_command(".ra 50")
        penalty = self.run_command(".rcp 50")
        self.assertEqual(normal.command, "rc")
        self.assertEqual(normal.metadata["target"], 50)
        self.assertEqual(bonus.metadata["target"], 50)
        self.assertEqual(penalty.metadata["target"], 50)
        self.assertEqual(bonus.metadata["mode"], "bonus")
        self.assertEqual(penalty.metadata["mode"], "penalty")

    def test_rc_reads_card_attributes_difficulty_and_hidden_mode(self):
        card = self.router.identities.characters.create(
            self.context.actor,
            "调查员",
            attributes={"幸运": 60, "__DefaultDice": "d100"},
        )
        self.router.identities.characters.bind(
            self.context.actor, self.context.source, card.card_id
        )
        check = self.run_command(".rc 困难幸运")
        hidden = self.run_command(".rc _幸运")
        self.assertEqual(check.metadata["target"], 30)
        self.assertEqual(hidden.metadata["hidden"], True)
        self.assertIn("隐藏", hidden.rendered)

    def test_coc_and_coc6_generate_and_bind_cards(self):
        generated = self.run_command(".coc6d")
        self.assertEqual(generated.metadata["variant"], 6)
        self.assertTrue(generated.metadata["detailed"])
        self.assertEqual(generated.result.system, "COC6")
        current = self.router.identities.characters.resolve(self.context)
        self.assertEqual(current.card_id, generated.result.card_id)

    def test_st_can_set_show_increment_delete_and_clear(self):
        self.run_command(".st 力量:50 敏捷:40")
        self.run_command(".st 幸运50")
        self.assertEqual(self.run_command(".st show 幸运").result, {"幸运": 50})
        self.assertEqual(self.run_command(".st show 力量").result, {"力量": 50})
        self.run_command(".st 力量+5")
        self.assertEqual(self.run_command(".st show 力量").result, {"力量": 55})
        self.run_command(".st del 敏捷")
        self.assertEqual(self.run_command(".st show 敏捷").result, {})
        self.run_command(".st clr")
        self.assertEqual(self.run_command(".st show").result, {})

    def test_sc_updates_san_and_ri_returns_initiative(self):
        self.run_command(".st san:50")
        sanity = self.run_command(".sc 1/1d6 50")
        self.assertIn("remaining", sanity.result)
        initiative = self.run_command(".ri+2 2#调查员")
        self.assertEqual(initiative.metadata["offset"], 2)
        self.assertEqual(len(initiative.result), 2)

        fixed = self.run_command(".ri 17 boss")
        self.assertEqual(fixed.result, [{"name": "boss", "value": 17}])
        self.assertEqual(fixed.metadata["explicit_value"], 17)

        expression = self.run_command(".ri d20 boss")
        self.assertEqual(expression.metadata["expression"], "d20")

    def test_help_custom_commands_and_input_validation(self):
        help_response = self.run_command(".help rc")
        self.assertIn("rc", help_response.result)

        def custom_handler(context, args, metadata):
            return type(help_response)("custom", args, {"ok": True}, "ok", metadata)

        self.router.register("custom", custom_handler)
        self.assertEqual(self.run_command(".custom value").result, {"ok": True})
        with self.assertRaises(UnknownCommandError):
            self.run_command(".missing")
        with self.assertRaises(CommandError):
            self.run_command("not-a-command")


if __name__ == "__main__":
    unittest.main()
