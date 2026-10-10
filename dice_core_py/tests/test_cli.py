import json
import subprocess
import sys
import unittest


class CliTest(unittest.TestCase):
    def test_module_cli_returns_json(self):
        completed = subprocess.run(
            [sys.executable, "-m", "trpg_dice.cli", "1", "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["expression"], "1")

    def test_module_cli_returns_human_readable_output(self):
        completed = subprocess.run(
            [sys.executable, "-m", "trpg_dice.cli", "1"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("= 1", completed.stdout)


if __name__ == "__main__":
    unittest.main()
