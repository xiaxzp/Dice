import tempfile
import unittest

from trpg_dice import (
    ActorRef,
    CommandRouter,
    DiceEngine,
    DiceSession,
    DiceRoller,
    IdentityServices,
    MessageContext,
    MessageSource,
    ProfileRepository,
    SeededRandomSource,
)


class ManualCommandCoverageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.identities = IdentityServices(ProfileRepository(self.temp_dir.name))
        self.session = DiceSession("manual", rng=SeededRandomSource(42))
        self.router = CommandRouter(
            DiceEngine(self.identities, DiceRoller(SeededRandomSource(42))),
            session=self.session,
        )
        self.context = MessageContext(
            ActorRef("cli", "user"),
            MessageSource("cli", "group", "room"),
            account_nickname="用户",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_command(self, text):
        return self.router.execute(self.context, text)

    def test_manual_core_command_families(self):
        commands = (
            ".help", ".r d6", ".ob join", ".set 20", ".name en 2", ".nn 角色",
            ".coc", ".dnd", ".pc list", ".st hp:10", ".setcoc 2", ".rc 50",
            ".sc 0/1 50", ".ti", ".li", ".en hp 10", ".ri 5 boss", ".init",
            ".w 2a8", ".ww 2a8", ".me 做了个动作", ".jrrp", ".welcome 欢迎",
            ".welcome show", ".deck new roles=wolf|villager", ".deck show",
            ".draw roles", ".ak new 分歧", ".ak add A|B", ".ak get",
            ".rules dnd:language", ".log new session",
        )
        for command in commands:
            with self.subTest(command=command):
                response = self.run_command(command)
                self.assertTrue(response.command)

    def test_manual_stateful_operations(self):
        self.assertEqual(self.run_command(".ob on").result["enabled"], True)
        self.assertEqual(self.run_command(".ob off").result["enabled"], False)
        self.run_command(".ob join")
        self.assertEqual(len(self.run_command(".ob list").result), 1)
        self.run_command(".ob exit")
        self.assertEqual(self.run_command(".ob list").result, [])

        self.run_command(".nn kp")
        self.assertEqual(self.run_command(".r d4").result.display_name, "kp")
        self.run_command(".nn del")
        self.assertEqual(self.run_command(".r d4").result.display_name, "用户")
        self.run_command(".nn 全部清空")
        self.assertEqual(self.run_command(".nn clr").result, 1)

        self.run_command(".deck new roles=wolf|villager")
        self.assertEqual(self.run_command(".deck show").result["roles"], 2)
        self.run_command(".draw roles")
        self.assertEqual(self.run_command(".deck show").result["roles"], 1)
        self.run_command(".deck reset roles")
        self.assertEqual(self.run_command(".deck show").result["roles"], 2)
        self.run_command(".deck clr")
        self.assertEqual(self.run_command(".deck show").result, {})

        self.run_command(".ak new title")
        self.run_command(".ak add one|two")
        selected = self.run_command(".ak get").result
        self.assertIn(selected, {"one", "two"})
        self.assertEqual(self.session.data["ank"]["options"], [])
        self.run_command(".ak clr")
        self.assertEqual(self.run_command(".ak show").result["options"], [])

    def test_manual_compact_aliases_and_parameter_forms(self):
        self.assertEqual(self.run_command(".r3#p").metadata["repeat"], 3)
        self.assertEqual(self.run_command(".rb").result.result.terms[0].kind, "bonus")
        self.assertEqual(self.run_command(".rp").result.result.terms[0].kind, "penalty")
        self.assertEqual(self.run_command(".nnn jp").result, self.run_command(".r d4").result.display_name)

        self.run_command(".ak#title")
        self.run_command(".ak+one|two")
        self.assertEqual(self.run_command(".ak show").result["options"], ["one", "two"])
        self.run_command(".ak-1")
        self.assertEqual(self.run_command(".ak show").result["options"], ["two"])
        self.assertEqual(self.run_command(".ak= ").result, "two")

        self.run_command(".deck set numbers=range 1 3")
        self.assertEqual(self.run_command(".deck show numbers").result["numbers"]["entries"][0]["value"], "1")
        self.assertTrue(self.run_command(".drawh numbers").metadata["hidden"])

        self.run_command(".st san:70")
        sanity = self.run_command(".sc 0/1 直面外神")
        self.assertEqual(sanity.metadata["reason"], "直面外神")

        self.assertEqual(self.run_command(".ri2DK boss").metadata["expression"], "2d20k1")
        self.run_command(".init clr")
        self.assertEqual(self.run_command(".init").result, [])

    def test_manual_reason_before_expression_and_auto_success(self):
        roll = self.run_command(".r 伤害:d6")
        self.assertEqual(roll.result.request.expression, "d6")
        self.assertEqual(roll.result.request.reason, "伤害")

        self.run_command(".st 爆破:10")
        check = self.run_command(".rc 自动成功爆破")
        self.assertTrue(check.metadata["auto_success"])
        self.assertTrue(check.result.success)

    def test_st_accepts_name_and_trailing_number_without_separator(self):
        self.run_command(".st hp50 mp12")
        self.assertEqual(self.run_command(".st show hp").result, {"hp": 50})
        self.assertEqual(self.run_command(".st show mp").result, {"mp": 12})

    def test_manual_private_bindings_are_global(self):
        private_context = MessageContext(
            self.context.actor,
            MessageSource("cli", "private", "direct"),
            account_nickname="用户",
        )
        self.router.execute(private_context, ".nn 全局称呼")
        self.assertEqual(self.identities.nicknames.resolve(private_context), "全局称呼")
        created = self.router.execute(private_context, ".pc new private-card")
        self.router.execute(private_context, ".pc tag private-card")
        self.assertEqual(
            self.identities.characters.resolve(private_context).card_id,
            created.result.card_id,
        )

    def test_manual_pc_operations(self):
        created = self.run_command(".pc new investigator")
        self.assertEqual(created.result.name, "investigator")
        self.run_command(".pc tag investigator")
        self.run_command(".st 力量:60")
        self.assertEqual(self.run_command(".pc show").result["attributes"]["力量"], 60)
        self.run_command(".pc nn renamed")
        self.assertEqual(self.run_command(".pc show").result["name"], "renamed")
        self.run_command(".pc del")
        self.assertEqual(self.run_command(".pc show").result, {})

    def test_manual_pc_copy_clear_and_card_expression_pool(self):
        self.run_command(".pc new investigator")
        self.run_command(".pc tag investigator")
        self.run_command(".st 敏捷:2 &剑=1d6")
        self.assertEqual(self.run_command(".st show 剑").result["剑"], "1d6")
        self.run_command(".pc cpy copy=investigator")
        self.run_command(".pc tag copy")
        pool = self.run_command(".ww 敏捷+剑")
        self.assertEqual(pool.command, "ww")
        self.assertGreaterEqual(pool.result.count, 1)
        self.run_command(".pc clr")
        self.assertEqual(self.run_command(".pc list").result, [])

    def test_manual_switch_and_lifecycle_subcommands(self):
        self.assertEqual(self.run_command(".set 20").result["default_sides"], 20)
        self.assertEqual(self.run_command(".set").result["default_sides"], 100)
        self.assertEqual(self.run_command(".me off").result, False)
        self.assertEqual(self.run_command(".me on").result, True)
        self.assertEqual(self.run_command(".jrrp off").result, False)
        self.assertEqual(self.run_command(".jrrp on").result, True)
        self.run_command(".welcome 欢迎{nick}")
        self.assertEqual(self.run_command(".welcome clr").result, None)
        self.run_command(".rules set dnd")
        self.assertEqual(self.session.data["rules_default"], "dnd")
        self.run_command(".rules set")
        self.assertIsNone(self.session.data["rules_default"])
        self.run_command(".log new session")
        self.assertTrue(self.run_command(".log off").result["enabled"] is False)
        self.assertTrue(self.run_command(".log on").result["enabled"])
        self.assertTrue(self.run_command(".log end").result["enabled"] is False)

        created = self.run_command(".pc new builder")
        self.run_command(".pc tag builder")
        built = self.run_command(".pc build builder")
        self.assertEqual(built.result.card_id, created.result.card_id)
        redone = self.run_command(".pc redo builder")
        self.assertEqual(redone.result.card_id, created.result.card_id)
        self.assertEqual(self.run_command(".pc stat").result, {})

    def test_document_boundary_commands_are_explicitly_adapter_owned(self):
        for command in (
            ".bot on", ".reply off", ".dismiss", "!authorize reason",
            ".send message", ".group state", ".rdc", ".rdx", ".rsr",
            ".rnc", ".rfc", ".rbh", ".rws",
        ):
            with self.subTest(command=command):
                response = self.run_command(command)
                self.assertTrue(response.metadata["platform_boundary"])
                self.assertEqual(response.result["handled_by"], "adapter")

    def test_help_lists_manual_commands_and_suggests_close_matches(self):
        result = self.run_command(".help")
        for command in ("ob", "set", "pc", "setcoc", "draw/deck", "ak", "rdc"):
            self.assertIn(command, result.result)
        suggestion = self.run_command(".help ruls")
        self.assertIn("rules", suggestion.result)


if __name__ == "__main__":
    unittest.main()
