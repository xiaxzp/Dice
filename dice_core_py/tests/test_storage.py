import tempfile
import unittest
from pathlib import Path

from trpg_dice import StorageError
from trpg_dice.storage import JsonStore


class StorageTest(unittest.TestCase):
    def test_json_store_round_trip_is_utf8(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonStore(root)
            store.write("nested/data.json", {"名称": "调查员", "number": 3})
            self.assertEqual(store.read("nested/data.json"), {"名称": "调查员", "number": 3})

    def test_invalid_json_and_non_object_roots_raise(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonStore(root)
            path = Path(root) / "invalid.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(StorageError):
                store.read("invalid.json")
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(StorageError):
                store.read("invalid.json")

    def test_write_failure_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonStore(root)
            store.write("data.json", {"stable": True})
            with self.assertRaises(StorageError):
                store.write("data.json", {"not_json": object()})
            self.assertEqual(store.read("data.json"), {"stable": True})

    def test_delete_and_path_escape_protection(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonStore(root)
            store.write("data.json", {})
            self.assertTrue(store.delete("data.json"))
            self.assertFalse(store.delete("data.json"))
            with self.assertRaises(StorageError):
                store.write("../outside.json", {})


if __name__ == "__main__":
    unittest.main()
