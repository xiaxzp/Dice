import unittest

from trpg_dice import (
    DiceExpressionError,
    DiceLimitError,
    DiceRoller,
    DivisionByZeroError,
    RollLimits,
    SequenceRandomSource,
)


class RollExpressionsTest(unittest.TestCase):
    def test_default_expression_and_normalization_aliases(self):
        roller = DiceRoller(SequenceRandomSource([100, 1, 6, 1]), default_sides=20)
        self.assertEqual(roller.normalize(""), "1d20")
        self.assertEqual(roller.normalize("D"), "1d20")
        self.assertEqual(roller.normalize("2D6x3"), "2d6*3")
        self.assertEqual(roller.normalize(" 2 d 6 + 1 "), "2d6+1")

    def test_plain_dice_numbers_and_arithmetic(self):
        result = DiceRoller(SequenceRandomSource([1, 6])).roll("2d6+3")
        self.assertEqual(result.total, 10)
        self.assertEqual(result.terms[0].rolls, (1, 6))
        self.assertEqual(DiceRoller().roll("5").total, 5)

    def test_operator_precedence_and_parentheses(self):
        roller = DiceRoller()
        self.assertEqual(roller.roll("2+3*4").total, 14)
        self.assertEqual(roller.roll("(2+3)*4").total, 20)
        self.assertEqual(roller.roll("-5/2").total, -2)
        self.assertEqual(roller.roll("-(5/2)").total, -2)

    def test_keep_highest_preserves_roll_details(self):
        result = DiceRoller(SequenceRandomSource([1, 6, 4, 5])).roll("4d6k3")
        self.assertEqual(result.total, 15)
        self.assertEqual(result.terms[0].kept, (6, 4, 5))
        self.assertEqual(result.terms[0].dropped, (1,))

    def test_expression_limits_and_invalid_syntax(self):
        roller = DiceRoller()
        for expression in ("0d6", "d0", "4d6k5", "d6/0", "2d6+"):
            expected = DivisionByZeroError if expression == "d6/0" else DiceExpressionError
            with self.assertRaises(expected):
                roller.roll(expression)
        limited = DiceRoller(limits=RollLimits(max_dice_count=2))
        with self.assertRaises(DiceLimitError):
            limited.roll("3d6")

    def test_result_rendering_contains_expression_and_details(self):
        result = DiceRoller(SequenceRandomSource([2])).roll("d6")
        rendered = result.render()
        self.assertIn("1d6 = 2", rendered)
        self.assertIn("[2]", rendered)


if __name__ == "__main__":
    unittest.main()
