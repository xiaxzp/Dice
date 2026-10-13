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
    SequenceRandomSource,
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

    def test_c_style_roll_rendering_matches_complete_and_multi_roll_shapes(self):
        response = self.run_command(".r 2d6+3")
        self.assertRegex(response.rendered, r"2D6\+3\=\d+\+\d+\+3\=\d+\+3\=\d+")
        repeated = self.run_command(".r2#2d6")
        self.assertRegex(repeated.rendered, r"2D6=\d+\+\d+=\d+, \d+\+\d+=\d+")

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

    def test_w_and_ww_use_c_style_pool_rendering(self):
        short = self.run_command(".w 2a8")
        detailed = self.run_command(".ww 2a8")
        self.assertIn("掷骰: 2a8=", short.rendered)
        self.assertIn("掷骰: 2a8={", detailed.rendered)
        self.assertEqual(short.metadata["target"], 8)
        self.assertEqual(short.metadata["explode_at"], 8)
        self.assertNotIn("成功数：", short.rendered)

        repeated = self.run_command(".ww2#2a10")
        hidden = self.run_command(".wwh 2a8")
        self.assertEqual(repeated.metadata["repeat"], 2)
        self.assertIn("private_rendered", hidden.metadata)
        self.assertIn("暗骰", hidden.rendered)

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

    def test_coc7_reports_totals_without_and_with_luck(self):
        generated = self.run_command(".coc")
        without_luck = sum(
            generated.result[name]
            for name in ("力量", "体质", "体型", "敏捷", "外貌", "智力", "意志", "教育")
        )
        with_luck = without_luck + generated.result["幸运"]
        self.assertEqual(generated.result["不含幸运合计"], without_luck)
        self.assertEqual(generated.result["含幸运合计"], with_luck)
        self.assertIn(f"共计:{without_luck}/{with_luck}", generated.rendered)

    def test_coc_output_matches_original_simple_and_detailed_shapes(self):
        simple_coc7 = self.run_command(".coc")
        self.assertIn("的调查员作成:\n力量:", simple_coc7.rendered)
        self.assertIn(" 共计:", simple_coc7.rendered)

        simple_coc6 = self.run_command(".coc6")
        self.assertIn("的调查员作成:\n力量:", simple_coc6.rendered)
        self.assertIn("共计:", simple_coc6.rendered)
        self.assertIn("资产:", simple_coc6.rendered)

        detailed_coc7 = self.run_command(".cocd")
        self.assertIn("力量STR=3D6*5=", detailed_coc7.rendered)
        self.assertIn("伤害奖励DB=", detailed_coc7.rendered)
        self.assertIn("移动力MOV=", detailed_coc7.rendered)

        detailed_coc6 = self.run_command(".coc6d")
        self.assertIn("力量STR=3D6=", detailed_coc6.rendered)
        self.assertIn("资产=1D10=", detailed_coc6.rendered)

    def test_st_can_set_show_increment_delete_and_clear(self):
        self.run_command(".st 力量:50 敏捷:40")
        self.run_command(".st 幸运50")
        self.assertEqual(self.run_command(".st show 幸运").result, {"幸运": 50})
        self.assertEqual(self.run_command(".st show 力量").result, {"力量": 50})
        self.run_command(".st 力量+5")
        self.assertEqual(self.run_command(".st show 力量").result, {"力量": 55})
        self.run_command(".st del 敏捷")
        with self.assertRaisesRegex(CommandError, "属性敏捷不存在"):
            self.run_command(".st show 敏捷")
        self.run_command(".st clr")
        self.assertEqual(self.run_command(".st show").result, {})

    def test_st_matches_original_help_missing_card_and_rendering(self):
        self.assertIn("属性记录", self.run_command(".st").rendered)
        with self.assertRaisesRegex(CommandError, "角色卡记录"):
            self.run_command(".st show")
        with self.assertRaisesRegex(CommandError, "角色卡记录"):
            self.run_command(".st clr")

        self.run_command(".pc new investigator")
        self.run_command(".pc tag investigator")
        self.run_command(".st 敏捷:50 力量:60")
        shown = self.run_command(".st show")
        self.assertLess(shown.rendered.index("力量:60"), shown.rendered.index("敏捷:50"))
        self.assertIn("闪避:25", shown.rendered)
        with self.assertRaisesRegex(CommandError, "属性幸运不存在"):
            self.run_command(".st del 幸运")

    def test_nickname_initiative_and_pc_subcommands_use_original_templates(self):
        self.assertIn("称呼", self.run_command(".nn").rendered)
        self.assertIn("人物卡管理", self.run_command(".pc").rendered)
        self.assertIn("先攻", self.run_command(".init").rendered)
        self.assertIn("没有保存先攻表", self.run_command(".init show").rendered)

        self.run_command(".nn keeper")
        deleted = self.run_command(".nn del")
        self.assertIn("keeper", deleted.rendered)
        self.assertNotIn("True", deleted.rendered)

        self.run_command(".pc new source")
        self.run_command(".pc tag source")
        copied = self.run_command(".pc cpy copy=source")
        self.assertIn("已将「source」的属性复制到「copy」", copied.rendered)
        self.assertIn("各群角色列表", self.run_command(".pc grp").rendered)
        self.assertIn("模板类", self.run_command(".pc type").rendered)
        self.assertIn("<COC7>source", self.run_command(".pc tojson").rendered)

    def test_stateful_command_outputs_match_original_boundaries(self):
        for command, keyword in (
            (".ob", "旁观状态"),
            (".game", "跑团会话"),
            (".deck", "抽牌和牌堆"),
            (".draw", "抽牌和牌堆"),
            (".ak", "安价分歧"),
            (".log", "日志状态"),
        ):
            with self.subTest(command=command):
                self.assertIn(keyword, self.run_command(command).rendered)

        self.run_command(".game new table")
        self.run_command(".ob join")
        self.assertIn(self.context.actor.user_id, self.run_command(".ob list").rendered)
        self.run_command(".ob exit")
        self.assertIn("暂无旁观者", self.run_command(".ob clr").rendered)

        self.assertIn("清除失败", self.run_command(".welcome clr").rendered)
        self.run_command(".deck new cards=A|B")
        drawn = self.run_command(".draw cards 2")
        self.assertRegex(drawn.rendered, r"(?:A\|B|B\|A)")
        with self.assertRaisesRegex(CommandError, "没听说过"):
            self.run_command(".draw missing")
        with self.assertRaisesRegex(CommandError, "没听说过"):
            self.run_command(".deck show missing")

        self.run_command(".ak new choice")
        self.run_command(".ak add yes|no")
        self.assertRegex(self.run_command(".ak get").rendered, r"选择：[12]\. ")

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
        self.assertIn("D20+2=", initiative.rendered)

        fixed = self.run_command(".ri 17 boss")
        self.assertEqual(fixed.result, [{"name": "boss", "value": 17}])
        self.assertEqual(fixed.metadata["explicit_value"], 17)
        self.assertTrue(fixed.rendered.endswith("17"))

        expression = self.run_command(".ri d20 boss")
        self.assertEqual(expression.metadata["expression"], "d20")

    def test_set_matches_original_bounds_and_errors(self):
        self.assertEqual(self.run_command(".set 9999").result["default_sides"], 9999)
        with self.assertRaisesRegex(CommandError, "默认骰不能为零"):
            self.run_command(".set 0")
        for value in ("10000", "not-a-number"):
            with self.subTest(value=value), self.assertRaisesRegex(
                CommandError, "1-9999"
            ):
                self.run_command(f".set {value}")

    def test_madness_uses_complete_distinct_fear_and_mania_tables(self):
        self.router = CommandRouter(
            DiceEngine(
                self.router.identities,
                DiceRoller(SequenceRandomSource([9, 1, 100])),
            )
        )
        fear = self.run_command(".ti")
        self.assertEqual(fear.result["detail_roll"], "1D100=100")
        self.assertIn("动物恐惧症（Zoophobia）", fear.rendered)
        self.assertIn("守秘人也可以自行从恐惧症状表中选择其他症状", fear.rendered)

        self.router = CommandRouter(
            DiceEngine(
                self.router.identities,
                DiceRoller(SequenceRandomSource([10, 2, 100])),
            )
        )
        mania = self.run_command(".li")
        self.assertEqual(mania.result["detail_roll"], "1D100=100")
        self.assertIn("喜兽癖（Zoomania）", mania.rendered)
        self.assertIn("KP也可以自行从躁狂症状表中选择其他症状", mania.rendered)

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
