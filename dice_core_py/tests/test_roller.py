import unittest

from trpg_dice import (
    DiceExpressionError,
    DiceLimitError,
    DiceRoller,
    DivisionByZeroError,
    SequenceRandomSource,
    coc_success_level,
)


class DiceRollerTest(unittest.TestCase):
    def test_normal_dice_and_arithmetic(self):
        result = DiceRoller(SequenceRandomSource([1, 6])).roll("2d6+3")
        self.assertEqual(result.total, 10)
        self.assertEqual(result.terms[0].rolls, (1, 6))
        self.assertEqual(result.normalized_expression, "2d6+3")

    def test_parentheses_and_negative_division_truncate_toward_zero(self):
        roller = DiceRoller()
        self.assertEqual(roller.roll("-(5/2)").total, -2)
        self.assertEqual(roller.roll("-5/2").total, -2)
        self.assertEqual(roller.roll("(2+3)*4").total, 20)

    def test_keep_highest(self):
        result = DiceRoller(SequenceRandomSource([1, 6, 4, 5])).roll("4d6k3")
        self.assertEqual(result.total, 15)
        self.assertEqual(result.terms[0].kept, (6, 4, 5))
        self.assertEqual(result.terms[0].dropped, (1,))

    def test_fate_dice_aliases(self):
        for expression in ("f", "df", "4df", "6f"):
            result = DiceRoller(SequenceRandomSource([-1, 0, 1, 1, 0, -1])).roll(expression)
            self.assertEqual(result.total, 1 if expression != "6f" else 0)
            self.assertEqual(result.terms[0].kind, "fate")

    def test_bonus_and_penalty_use_tens(self):
        bonus = DiceRoller(SequenceRandomSource([56, 3])).roll("b")
        penalty = DiceRoller(SequenceRandomSource([56, 8])).roll("p")
        self.assertEqual(bonus.total, 26)
        self.assertEqual(penalty.total, 76)

    def test_bonus_and_penalty_preserve_zero_ones(self):
        bonus = DiceRoller(SequenceRandomSource([100, 1])).roll("b")
        penalty = DiceRoller(SequenceRandomSource([100, 10])).roll("p")
        self.assertEqual(bonus.total, 10)
        self.assertEqual(penalty.total, 100)

    def test_limits_and_errors(self):
        roller = DiceRoller()
        with self.assertRaises(DiceExpressionError):
            roller.roll("0d6")
        with self.assertRaises(DiceExpressionError):
            roller.roll("d0")
        with self.assertRaises(DivisionByZeroError):
            roller.roll("d6/0")
        with self.assertRaises(DiceExpressionError):
            roller.roll("4d6k5")
        with self.assertRaises(DiceLimitError):
            roller.roll("1001d6")

    def test_pool_and_coc(self):
        pool = DiceRoller(SequenceRandomSource([8, 10, 7])).pool(2)
        self.assertEqual(pool.rolls, (8, 10, 7))
        self.assertEqual(pool.successes, 2)
        self.assertEqual(coc_success_level(1, 50), "critical")
        self.assertEqual(coc_success_level(100, 50), "fumble")
        self.assertEqual(coc_success_level(40, 50), "regular_success")


if __name__ == "__main__":
    unittest.main()
