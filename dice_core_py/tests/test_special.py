import unittest

from trpg_dice import (
    Deck,
    DeckEntry,
    L5RDicePool,
    Roulette,
    SequenceRandomSource,
)


class SpecialDiceTest(unittest.TestCase):
    def test_roulette_uses_each_face_before_reset(self):
        roulette = Roulette(3, rng=SequenceRandomSource([0, 0, 0, 0]))
        self.assertEqual([roulette.roll(), roulette.roll(), roulette.roll()], [1, 2, 3])
        self.assertEqual(roulette.remaining, 0)
        self.assertEqual(roulette.roll(), 1)

    def test_weighted_deck_and_state_round_trip(self):
        deck = Deck(
            [DeckEntry("rare", 1), DeckEntry("common", 3)],
            rng=SequenceRandomSource([1, 3]),
        )
        self.assertEqual(deck.draw().value, "rare")
        restored = Deck.from_dict(deck.to_dict(), rng=SequenceRandomSource([1]))
        self.assertEqual(restored.remaining, 1)
        self.assertEqual(restored.draw().value, "common")

    def test_l5r_additional_die_and_base64_round_trip(self):
        pool = L5RDicePool(SequenceRandomSource([2, 5, 7]))
        pool.insert_white(1)
        pool.insert_black(1, additional=True)
        rolled = pool.roll()
        self.assertEqual(rolled[0].result, 5)
        self.assertEqual(rolled[1].result, 2)
        self.assertEqual(rolled[1].status, "additional")
        decoded = L5RDicePool.decode(pool.encode())
        self.assertEqual(decoded.to_dict(), pool.to_dict())


if __name__ == "__main__":
    unittest.main()
