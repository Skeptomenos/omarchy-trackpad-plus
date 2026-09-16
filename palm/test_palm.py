"""Palm quirks template stays valid and more aggressive than stock Apple 1600."""

import configparser
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

TEMPLATE = Path(__file__).with_name("local-overrides.quirks")
SCRIPT = Path(__file__).with_name("palm-settings")


class PalmQuirksTests(unittest.TestCase):
    def test_template_parses_with_two_device_sections(self):
        parser = configparser.ConfigParser(strict=True, interpolation=None)
        parser.optionxform = str
        parser.read(TEMPLATE)
        self.assertEqual(len(parser.sections()), 2)

    def test_thresholds_aggressive_but_sane(self):
        parser = configparser.ConfigParser(strict=True, interpolation=None)
        parser.optionxform = str
        parser.read(TEMPLATE)
        for section in parser.sections():
            self.assertEqual(parser[section]["MatchUdevType"], "touchpad")
            threshold = int(parser[section]["AttrPalmSizeThreshold"])
            self.assertGreaterEqual(threshold, 100)
            self.assertLess(threshold, 1600)

    def test_covers_spi_and_mtp(self):
        text = TEMPLATE.read_text()
        self.assertIn("MatchBus=spi", text)
        self.assertIn("MatchVendor=0x06CB", text)
        self.assertIn("MatchName=Apple*MTP*", text)


class PalmSettingsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.template = Path(temp.name) / "tpl.quirks"
        self.dest = Path(temp.name) / "out.quirks"
        shutil.copy(TEMPLATE, self.template)
        import os
        self.env = dict(os.environ, PALM_TEMPLATE=str(self.template), PALM_DEST=str(self.dest))

    def run_cli(self, *args):
        return subprocess.run(["bash", str(SCRIPT), *args], env=self.env,
                              text=True, capture_output=True, timeout=30)

    def test_get_reports_staged_threshold(self):
        result = self.run_cli("get")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "1000")

    def test_set_updates_both_stanzas(self):
        result = self.run_cli("set", "800")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "800")
        text = self.template.read_text()
        self.assertEqual(text.count("AttrPalmSizeThreshold=800"), 2)
        parser = configparser.ConfigParser(strict=True, interpolation=None)
        parser.optionxform = str
        parser.read(self.template)
        self.assertEqual(len(parser.sections()), 2)

    def test_set_rejects_out_of_range_and_unknown_commands(self):
        for args in (["set", "50"], ["set", "1601"], ["set", "many"], ["bogus"], []):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 64)
        self.assertIn("AttrPalmSizeThreshold=1000", self.template.read_text())

    def test_status_reports_missing_dest(self):
        result = self.run_cli("status")
        self.assertEqual(result.returncode, 0)
        self.assertIn("staged=1000", result.stdout)
        self.assertIn("installed=missing", result.stdout)


if __name__ == "__main__":
    unittest.main()
