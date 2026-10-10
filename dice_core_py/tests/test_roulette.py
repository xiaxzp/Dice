import unittest

from trpg_dice import DiceExpressionError, Roulette, SequenceRandomSource


class RouletteTest(unittest.TestCase):
    def test_each_face_is_used_once_then_pool_resets(self):
        roulette = Roulette(3, rng=SequenceRandomSource([0, 0, 0, 0]))
        self.assertEqual([roulette.roll(), roulette.roll(), roulette.roll()], [1, 2, 3])
        self.assertEqual(roulette.remaining, 0)
        self.assertEqual(roulette.roll(), 1)

    def test_copies_and_state_round_trip(self):
        roulette = Roulette(2, copies=2, rng=SequenceRandomSource([0, 0]))
        self.assertEqual([roulette.roll(), roulette.roll()], [1, 1])
        restored = Roulette.from_dict(roulette.to_dict(), rng=SequenceRandomSource([0, 0]))
        self.assertEqual(restored.remaining, 2)
        self.assertEqual(sorted([restored.roll(), restored.roll()]), [2, 2])

    def test_invalid_saved_pool_is_rejected(self):
        with self.assertRaises(DiceExpressionError):
            Roulette.from_dict({"sides": 2, "copies": 1, "pool": [1, 1]})


if __name__ == "__main__":
    unittest.main()
