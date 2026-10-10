import tempfile
import unittest

from trpg_dice import (
    ActorRef,
    DeckEntry,
    DiceSession,
    MessageSource,
    SequenceRandomSource,
    SessionRepository,
)


class SessionTest(unittest.TestCase):
    def test_session_json_round_trip_preserves_sources_and_state(self):
        with tempfile.TemporaryDirectory() as root:
            repository = SessionRepository(root)
            rng = SequenceRandomSource([0, 1, 1, 1, 1])
            session = DiceSession("campaign", rng=rng)
            actor = ActorRef("qq", "7")
            session.add_source(MessageSource("qq", "group", "8"))
            session.add_player(actor)
            session.configure_roulette(2)
            session.configure_deck("items", [DeckEntry("sword"), DeckEntry("potion")])
            session.roll(2)
            session.draw("items")
            repository.save(session)

            restored = repository.load("campaign", rng=SequenceRandomSource([0]))
            self.assertEqual(len(restored.sources), 1)
            self.assertIn(actor, restored.players)
            self.assertEqual(restored.roulettes[2].remaining, 1)
            self.assertEqual(restored.decks["items"].remaining, 1)


if __name__ == "__main__":
    unittest.main()
