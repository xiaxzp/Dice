import unittest

from trpg_dice import Deck, DeckEntry, DiceExpressionError, SequenceRandomSource


class DeckTest(unittest.TestCase):
    def test_weighted_non_replacement_deck_and_auto_reset(self):
        deck = Deck(
            [DeckEntry("rare", 1), DeckEntry("common", 3)],
            rng=SequenceRandomSource([1, 1, 1]),
        )
        self.assertEqual(deck.draw().value, "rare")
        self.assertEqual(deck.draw().value, "common")
        self.assertEqual(deck.remaining, 0)
        self.assertEqual(deck.draw().value, "rare")

    def test_replacement_deck_keeps_all_entries(self):
        deck = Deck(
            [DeckEntry("one"), DeckEntry("two")],
            replace=True,
            rng=SequenceRandomSource([1, 2, 1]),
        )
        self.assertEqual([deck.draw().value, deck.draw().value], ["one", "two"])
        self.assertEqual(deck.remaining, 2)

    def test_reset_and_state_round_trip(self):
        deck = Deck([DeckEntry("one"), DeckEntry("two")], rng=SequenceRandomSource([1]))
        deck.draw()
        restored = Deck.from_dict(deck.to_dict(), rng=SequenceRandomSource([1]))
        self.assertEqual(restored.remaining, 1)
        restored.reset()
        self.assertEqual(restored.remaining, 2)

    def test_invalid_deck_state_is_rejected(self):
        with self.assertRaises(DiceExpressionError):
            Deck.from_dict(
                {
                    "entries": [{"value": "one"}],
                    "remaining": [0, 0],
                }
            )


if __name__ == "__main__":
    unittest.main()
