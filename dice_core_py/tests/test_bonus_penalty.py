import unittest

from trpg_dice import DiceExpressionError, DiceLimitError, DiceRoller, SequenceRandomSource


class BonusPenaltyTest(unittest.TestCase):
    def test_bonus_selects_lowest_tens(self):
        result = DiceRoller(SequenceRandomSource([56, 3, 8])).roll("b2")
        self.assertEqual(result.total, 26)
        self.assertEqual(result.terms[0].extra_tens, (2, 7))

    def test_penalty_selects_highest_tens(self):
        result = DiceRoller(SequenceRandomSource([56, 3, 8])).roll("p2")
        self.assertEqual(result.total, 76)

    def test_zero_ones_use_ten_for_extra_dice(self):
        bonus = DiceRoller(SequenceRandomSource([100, 1, 10])).roll("b2")
        penalty = DiceRoller(SequenceRandomSource([100, 1, 10])).roll("p2")
        self.assertEqual(bonus.total, 10)
        self.assertEqual(penalty.total, 100)

    def test_single_letter_defaults_to_one(self):
        bonus = DiceRoller(SequenceRandomSource([56, 3])).bonus()
        penalty = DiceRoller(SequenceRandomSource([56, 8])).penalty()
        self.assertEqual(bonus.total, 26)
        self.assertEqual(penalty.total, 76)

    def test_bonus_penalty_count_has_a_safe_limit(self):
        roller = DiceRoller()
        with self.assertRaises(DiceExpressionError):
            roller.roll("b0")
        with self.assertRaises(DiceLimitError):
            roller.roll("b10")
        with self.assertRaises(DiceLimitError):
            roller.roll("p10")


if __name__ == "__main__":
    unittest.main()
