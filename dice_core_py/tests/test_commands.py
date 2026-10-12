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
        self.assertIn("测试用户掷骰 伤害:", response.rendered)

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

    def test_repeated_bonus_roll_interpolates_reason(self):
        response = self.run_command(".r3#b hh")
        self.assertEqual(response.metadata["reason"], "hh")
        self.assertIn("hh", response.rendered)
        self.assertNotIn("{reason}", response.rendered)

    def test_rc_ra_rcb_and_rcp_route_to_check_tools(self):
        normal = self.run_command(".rc 50")
        bonus = self.run_command(".ra 50")
        compact_bonus = self.run_command(".rcb 50")
        penalty = self.run_command(".rcp 50")
        self.assertEqual(normal.command, "rc")
        self.assertEqual(normal.metadata["target"], 50)
        self.assertEqual(bonus.metadata["target"], 50)
        self.assertEqual(penalty.metadata["target"], 50)
        self.assertEqual(bonus.metadata["mode"], "bonus")
        self.assertEqual(compact_bonus.metadata["mode"], "bonus")
        self.assertEqual(compact_bonus.metadata["bonus_dice"], 1)
        self.assertEqual(compact_bonus.result.roll.normalized_expression, "B1")
        self.assertEqual(penalty.metadata["mode"], "penalty")
        self.assertEqual(penalty.metadata["penalty_dice"], 1)
        self.assertEqual(penalty.result.roll.normalized_expression, "P1")

        two_bonus = self.run_command(".rcb2 50")
        two_penalty = self.run_command(".rcp2 50")
        self.assertEqual(two_bonus.metadata["bonus_dice"], 2)
        self.assertEqual(two_bonus.result.roll.normalized_expression, "B2")
        self.assertIn("B2=", two_bonus.rendered)
        self.assertIn("[奖励骰:", two_bonus.rendered)
        self.assertEqual(two_penalty.metadata["penalty_dice"], 2)
        self.assertEqual(two_penalty.result.roll.normalized_expression, "P2")
        self.assertIn("P2=", two_penalty.rendered)
        self.assertIn("[惩罚骰:", two_penalty.rendered)

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
        self.assertIn("暗中", hidden.rendered)

    def test_coc_generates_temporary_attributes_without_creating_or_binding_cards(self):
        generated = self.run_command(".coc6d")
        self.assertEqual(generated.metadata["variant"], 6)
        self.assertTrue(generated.metadata["detailed"])
        self.assertFalse(generated.metadata["persistent"])
        self.assertIsInstance(generated.result, dict)
        self.assertIn("力量", generated.result)
        self.assertNotIn("__Type", generated.result)
        self.assertEqual(self.router.identities.characters.list(self.context.actor), [])
        current = self.router.identities.characters.resolve(self.context)
        self.assertIsNone(current)

        self.run_command(".pc new investigator")
        self.run_command(".pc tag investigator")
        current = self.router.identities.characters.resolve(self.context)
        self.run_command(".coc")
        self.assertEqual(
            self.router.identities.characters.resolve(self.context).card_id,
            current.card_id,
        )

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

    def test_st_splits_adjacent_name_and_number_assignments(self):
        self.run_command(".st 射击40斗殴50")
        self.assertEqual(self.run_command(".st show 射击").result, {"射击": 40})
        self.assertEqual(self.run_command(".st show 斗殴").result, {"斗殴": 50})

    def test_st_hides_internal_statistics_from_attribute_lists(self):
        self.run_command(".pc new stats")
        self.run_command(".pc tag stats")
        self.run_command(".r d100")
        self.run_command(".rc 50")

        shown = self.run_command(".st show")
        listed = self.run_command(".st")
        for response in (shown, listed):
            self.assertNotIn("__StatD100Cnt", response.result)
            self.assertNotIn("__StatRcCnt", response.result)
            self.assertNotIn("__StatD100Cnt", response.rendered)
            self.assertNotIn("__StatRcCnt", response.rendered)
        self.assertGreater(self.run_command(".pc stat").result["dice"]["count"], 0)

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
