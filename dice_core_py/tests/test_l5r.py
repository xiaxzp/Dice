import unittest

from trpg_dice import DiceExpressionError, L5RDicePool, SequenceRandomSource


class L5RTest(unittest.TestCase):
    def test_insert_roll_and_symbol_mapping(self):
        pool = L5RDicePool(SequenceRandomSource([2, 5]))
        pool.insert_white(1)
        pool.insert_black(1)
        rolled = pool.roll()
        self.assertEqual([die.result for die in rolled], [2, 5])
        self.assertEqual(pool.result_symbols(), ("B", "S"))

    def test_additional_dice_keep_their_inserted_result(self):
        pool = L5RDicePool(SequenceRandomSource([5]))
        pool.insert_black(1, additional=True)
        self.assertEqual(pool.roll()[0].result, 5)
        self.assertEqual(pool.dice[0].status, "additional")

    def test_reroll_and_drop(self):
        pool = L5RDicePool(SequenceRandomSource([1, 2, 3]))
        pool.insert_white(2)
        pool.roll()
        pool.reroll(1)
        pool.drop(2)
        self.assertEqual(len(pool.result_symbols()), 1)
        with self.assertRaises(ValueError):
            pool.reroll(2)

    def test_json_and_base64_state_round_trip(self):
        pool = L5RDicePool(SequenceRandomSource([2]))
        pool.insert_white(1)
        pool.roll()
        self.assertEqual(L5RDicePool.from_dict(pool.to_dict()).to_dict(), pool.to_dict())
        self.assertEqual(L5RDicePool.decode(pool.encode()).to_dict(), pool.to_dict())

    def test_invalid_encoded_state_is_rejected(self):
        with self.assertRaises(DiceExpressionError):
            L5RDicePool.decode("not-base64")


if __name__ == "__main__":
    unittest.main()
