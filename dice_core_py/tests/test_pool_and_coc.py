import unittest

from trpg_dice import DiceExpressionError, DiceRoller, SequenceRandomSource, coc_success_level


class PoolAndCocTest(unittest.TestCase):
    def test_pool_counts_successes_and_explodes(self):
        result = DiceRoller(SequenceRandomSource([8, 10, 7])).pool(2)
        self.assertEqual(result.rolls, (8, 10, 7))
        self.assertEqual(result.successes, 2)
        self.assertEqual(result.to_dict()["explode_at"], 10)

    def test_pool_can_disable_explosions(self):
        result = DiceRoller(SequenceRandomSource([10, 10])).pool(2, explode_at=None)
        self.assertEqual(result.rolls, (10, 10))
        self.assertEqual(result.successes, 2)

    def test_pool_validates_count_target_and_sides(self):
        roller = DiceRoller()
        with self.assertRaises(DiceExpressionError):
            roller.pool(1, sides=6, target=7)
        with self.assertRaises(DiceExpressionError):
            roller.pool(1, sides=6, explode_at=8)

    def test_all_coc_rule_families_have_defined_levels(self):
        for rule in range(8):
            for value in (1, 5, 50, 96, 100):
                level = coc_success_level(value, 50, rule)
                self.assertIn(
                    level,
                    {"critical", "extreme_success", "hard_success", "regular_success", "failure", "fumble"},
                )

    def test_coc_check_returns_structured_result(self):
        check = DiceRoller(SequenceRandomSource([1])).coc_check(50)
        self.assertTrue(check.success)
        self.assertEqual(check.roll.total, 1)
        self.assertEqual(check.success_level, "critical")


if __name__ == "__main__":
    unittest.main()
