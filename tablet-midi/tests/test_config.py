"""Configuration: defaults, round-tripping and the rules it enforces."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tabletmidi.config import Config, ConfigError, default_config_path


class Defaults(unittest.TestCase):
    def test_defaults_are_valid_and_match_the_brief(self):
        cfg = Config().validate()
        self.assertEqual(cfg.layout.buttons, 10)
        self.assertEqual(cfg.layout.strip_at, "bottom")
        self.assertNotEqual(cfg.midi.cc_x, cfg.midi.cc_y)
        # Ten buttons on undefined controllers, clear of the two pad ones.
        self.assertEqual(
            list(range(cfg.midi.button_cc_base, cfg.midi.button_cc_base + 10)),
            list(range(20, 30)),
        )

    def test_sections_are_independent_between_instances(self):
        a, b = Config(), Config()
        a.midi.channel = 7
        self.assertEqual(b.midi.channel, 1, "dataclass defaults must not be shared")


class RoundTrip(unittest.TestCase):
    def test_save_then_load(self):
        cfg = Config()
        cfg.midi.channel = 5
        cfg.layout.buttons = 8
        cfg.area.x_min, cfg.area.x_max = 100, 900
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "config.json")
            cfg.save(path)
            again = Config.load(path)
        self.assertEqual(again.midi.channel, 5)
        self.assertEqual(again.layout.buttons, 8)
        self.assertEqual((again.area.x_min, again.area.x_max), (100, 900))

    def test_missing_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config.load_or_default(os.path.join(tmp, "absent.json"))
        self.assertEqual(cfg.layout.buttons, 10)

    def test_unknown_keys_are_reported_not_ignored(self):
        data = Config().to_dict()
        data["midi"]["cc_z"] = 3
        with self.assertRaises(ConfigError) as caught:
            Config.from_dict(data)
        self.assertIn("cc_z", str(caught.exception))

    def test_a_json_list_is_rejected(self):
        with self.assertRaises(ConfigError):
            Config.from_dict([])

    def test_written_file_is_readable_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.json")
            Config().save(path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertIn("behaviour", data)


class Rules(unittest.TestCase):
    def bad(self, **overrides):
        cfg = Config()
        for dotted, value in overrides.items():
            section, _, key = dotted.partition("__")
            setattr(getattr(cfg, section), key, value)
        with self.assertRaises(ConfigError) as caught:
            cfg.validate()
        return str(caught.exception)

    def test_channel_range(self):
        self.assertIn("channel", self.bad(midi__channel=0))
        self.assertIn("channel", self.bad(midi__channel=17))

    def test_controller_range(self):
        self.assertIn("cc_x", self.bad(midi__cc_x=128))
        self.assertIn("cc_y", self.bad(midi__cc_y=-1))

    def test_pad_controllers_must_differ(self):
        self.assertIn("differ", self.bad(midi__cc_x=17))

    def test_buttons_may_not_overlap_the_pad_controllers(self):
        # Ten buttons from CC 10 would cover 10-19, swallowing CC 16 and 17.
        self.assertIn("collides", self.bad(midi__button_cc_base=10))

    def test_buttons_must_fit_below_128(self):
        self.assertIn("127", self.bad(midi__button_cc_base=125))

    def test_on_and_off_must_differ(self):
        self.assertIn("differ", self.bad(midi__button_on=0))

    def test_strip_fraction(self):
        self.assertIn("strip", self.bad(layout__strip=0.0))
        self.assertIn("strip", self.bad(layout__strip=1.0))

    def test_strip_position(self):
        self.assertIn("strip_at", self.bad(layout__strip_at="left"))

    def test_at_least_one_button(self):
        self.assertIn("buttons", self.bad(layout__buttons=0))

    def test_high_resolution_needs_low_controller_numbers(self):
        # The LSB lives at CC+32, which does not exist above CC 31.
        self.assertIn("high_res", self.bad(midi__high_res=True, midi__cc_x=40))

    def test_high_resolution_lsb_may_not_hit_the_buttons(self):
        # CC 2 and 3 put their LSBs on 34 and 35; buttons from 30 cover those.
        msg = self.bad(
            midi__high_res=True, midi__cc_x=2, midi__cc_y=3,
            midi__button_cc_base=30,
        )
        self.assertIn("LSB", msg)

    def test_behaviour_fields(self):
        self.assertIn("xy_when", self.bad(behaviour__xy_when="always"))
        self.assertIn("smoothing", self.bad(behaviour__smoothing=1.0))
        self.assertIn("debounce", self.bad(behaviour__toggle_debounce_ms=-1))

    def test_area_bounds_must_be_ordered(self):
        self.assertIn("x_max", self.bad(area__x_min=900, area__x_max=100))

    def test_an_unset_maximum_is_allowed(self):
        cfg = Config()
        cfg.area.x_min, cfg.area.x_max = 0, 0
        cfg.validate()

    def test_high_resolution_default_layout_is_accepted(self):
        cfg = Config()
        cfg.midi.high_res = True
        cfg.validate()   # CC 16/17 -> LSBs on 48/49, buttons on 20-29


class Location(unittest.TestCase):
    def test_config_path_is_absolute_and_named(self):
        path = default_config_path()
        self.assertTrue(os.path.isabs(path))
        self.assertTrue(path.endswith(os.path.join("TabletMidi", "config.json")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
