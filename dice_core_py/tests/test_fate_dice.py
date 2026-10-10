import unittest

from trpg_dice import DiceExpressionError, DiceLimitError, DiceRoller, SequenceRandomSource


class FateDiceTest(unittest.TestCase):
    def test_fate_aliases_and_mapping(self):
        for expression in ("f", "df", "4df"):
            result = DiceRoller(SequenceRandomSource([-1, 0, 1, 1])).roll(expression)
            self.assertEqual(result.terms[0].kind, "fate")
            self.assertEqual(result.terms[0].rolls, (-1, 0, 1, 1))
            self.assertEqual(result.total, 1)

    def test_fate_count_can_be_explicit(self):
        result = DiceRoller(SequenceRandomSource([-1, 0, 1, -1, 1, 0])).roll("6f")
        self.assertEqual(result.total, 0)
        self.assertEqual(result.terms[0].count, 6)

    def test_fate_count_and_random_values_are_validated(self):
        with self.assertRaises(DiceExpressionError):
            DiceRoller().roll("0df")
        with self.assertRaises(DiceLimitError):
            DiceRoller().roll("1001df")
        with self.assertRaises(ValueError):
            DiceRoller(SequenceRandomSource([2])).roll("df")


if __name__ == "__main__":
    unittest.main()
