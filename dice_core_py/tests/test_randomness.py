import unittest

from trpg_dice import SeededRandomSource, SequenceRandomSource, SystemRandomSource


class RandomnessTest(unittest.TestCase):
    def test_sequence_source_is_inclusive_and_deterministic(self):
        source = SequenceRandomSource([1, 10])
        self.assertEqual(source.randint(1, 10), 1)
        self.assertEqual(source.randint(1, 10), 10)

    def test_sequence_source_rejects_out_of_range_and_exhaustion(self):
        with self.assertRaises(ValueError):
            SequenceRandomSource([0]).randint(1, 10)
        source = SequenceRandomSource([])
        with self.assertRaises(RuntimeError):
            source.randint(1, 10)

    def test_seeded_source_reproduces_a_sequence(self):
        left = SeededRandomSource(1234)
        right = SeededRandomSource(1234)
        self.assertEqual(
            [left.randint(1, 100) for _ in range(8)],
            [right.randint(1, 100) for _ in range(8)],
        )

    def test_system_source_returns_inclusive_values(self):
        source = SystemRandomSource()
        values = [source.randint(1, 1) for _ in range(4)]
        self.assertEqual(values, [1, 1, 1, 1])


if __name__ == "__main__":
    unittest.main()
