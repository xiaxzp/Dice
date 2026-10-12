import json
import subprocess
import sys
import tempfile
import unittest


class CommandCliTest(unittest.TestCase):
    def test_command_is_received_as_a_cli_parameter(self):
        with tempfile.TemporaryDirectory() as data_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "trpg_dice.command_cli",
                    ".r 1",
                    "--data-dir",
                    data_dir,
                    "--json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["command"], "r")
        self.assertEqual(payload["result"]["result"]["total"], 1)

    def test_command_cli_accepts_seed_and_full_source_parameters(self):
        with tempfile.TemporaryDirectory() as data_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "trpg_dice.command_cli",
                    "。r d20",
                    "--platform",
                    "discord",
                    "--user-id",
                    "42",
                    "--source-kind",
                    "channel",
                    "--source-id",
                    "7",
                    "--channel-id",
                    "9",
                    "--seed",
                    "1",
                    "--data-dir",
                    data_dir,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertIn("本地用户掷骰:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
