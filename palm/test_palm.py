"""Palm quirks template stays valid and more aggressive than stock Apple 1600."""

import configparser
import unittest
from pathlib import Path

TEMPLATE = Path(__file__).with_name("local-overrides.quirks")


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


if __name__ == "__main__":
    unittest.main()
