"""The behaviour of the tool, exercised without a tablet."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tabletmidi.config import Config
from tabletmidi.mapping import CC_STATUS, Mapper, MidiMsg, PenSample


def mapper(**overrides) -> Mapper:
    """A mapper over a 1000x1000 tablet, with smoothing off by default."""
    cfg = Config()
    cfg.behaviour.smoothing = 0.0
    for dotted, value in overrides.items():
        section, _, key = dotted.partition("__")
        setattr(getattr(cfg, section), key, value)
    return Mapper(cfg, 1000, 1000)


def ccs(messages):
    return [(m.data1, m.data2) for m in messages]


class Packing(unittest.TestCase):
    def test_short_message_layout(self):
        # status in the low byte, then the two data bytes.
        self.assertEqual(MidiMsg(0xB0, 16, 64).packed(), 0x004010B0)
        self.assertEqual(MidiMsg(0xB5, 127, 127).packed(), 0x7F7FB5)

    def test_channel_reaches_the_status_byte(self):
        m = mapper(midi__channel=10)
        out = m.feed(PenSample(0, 0, False, True, t=0))
        self.assertTrue(out)
        self.assertEqual(out[0].status, CC_STATUS | 9)


class Normalisation(unittest.TestCase):
    def test_spans_the_logical_range(self):
        m = mapper()
        self.assertEqual(m.normalise(0, 0), (0.0, 0.0))
        self.assertEqual(m.normalise(1000, 1000), (1.0, 1.0))
        self.assertEqual(m.normalise(500, 250), (0.5, 0.25))

    def test_clamps_outside_the_calibrated_box(self):
        m = mapper(area__x_min=200, area__x_max=800)
        self.assertEqual(m.normalise(100, 0)[0], 0.0)
        self.assertEqual(m.normalise(900, 0)[0], 1.0)
        self.assertAlmostEqual(m.normalise(500, 0)[0], 0.5)

    def test_inversion_and_swap(self):
        self.assertEqual(mapper(area__invert_x=True).normalise(250, 0)[0], 0.75)
        self.assertEqual(mapper(area__invert_y=True).normalise(0, 250)[1], 0.75)
        nx, ny = mapper(area__swap_xy=True).normalise(100, 900)
        self.assertAlmostEqual(nx, 0.9)
        self.assertAlmostEqual(ny, 0.1)

    def test_degenerate_bounds_do_not_divide_by_zero(self):
        m = mapper(area__x_min=500, area__x_max=0)
        m.x_limit = 400  # a maximum below the minimum
        self.assertEqual(m.normalise(500, 0)[0], 0.0)


class Strip(unittest.TestCase):
    def test_bottom_strip_boundary(self):
        m = mapper(layout__strip=0.2)
        self.assertFalse(m.in_strip(0.79))
        self.assertTrue(m.in_strip(0.80))
        self.assertTrue(m.in_strip(1.0))

    def test_top_strip_boundary(self):
        m = mapper(layout__strip=0.2, layout__strip_at="top")
        self.assertTrue(m.in_strip(0.0))
        self.assertTrue(m.in_strip(0.2))
        self.assertFalse(m.in_strip(0.21))

    def test_ten_cells_divide_the_width(self):
        m = mapper()
        self.assertEqual([m.cell_at(i / 10 + 0.05) for i in range(10)], list(range(10)))
        self.assertEqual(m.cell_at(0.0), 0)
        self.assertEqual(m.cell_at(1.0), 9, "the right edge belongs to the last cell")

    def test_pad_uses_the_full_controller_travel(self):
        m = mapper(layout__strip=0.2)
        self.assertEqual(m.pad_y(0.0), 0.0)
        self.assertAlmostEqual(m.pad_y(0.8), 1.0, places=6)
        top = mapper(layout__strip=0.2, layout__strip_at="top")
        self.assertEqual(top.pad_y(0.2), 0.0)
        self.assertAlmostEqual(top.pad_y(1.0), 1.0, places=6)


class Toggles(unittest.TestCase):
    def press(self, m, nx, t, ny=0.95):
        return m.feed(PenSample(nx * 1000, ny * 1000, True, True, t=t))

    def lift(self, m, nx, t, ny=0.95):
        return m.feed(PenSample(nx * 1000, ny * 1000, False, True, t=t))

    def test_tip_down_in_a_cell_toggles_it(self):
        m = mapper()
        self.assertEqual(ccs(self.press(m, 0.05, 0.0)), [(20, 127)])
        self.lift(m, 0.05, 0.1)
        self.assertEqual(ccs(self.press(m, 0.05, 1.0)), [(20, 0)])

    def test_each_cell_has_its_own_controller(self):
        m = mapper()
        for index in range(10):
            out = self.press(m, index / 10 + 0.05, index * 2.0)
            self.assertEqual(ccs(out), [(20 + index, 127)])
            self.lift(m, index / 10 + 0.05, index * 2.0 + 0.1)
        self.assertEqual(m.toggles, [True] * 10)

    def test_holding_the_tip_down_does_not_retrigger(self):
        m = mapper()
        self.press(m, 0.05, 0.0)
        for step in range(1, 6):
            self.assertEqual(self.press(m, 0.05, step), [])

    def test_dragging_into_the_strip_does_not_toggle(self):
        m = mapper()
        m.feed(PenSample(500, 400, True, True, t=0.0))     # tip down on the pad
        out = m.feed(PenSample(500, 950, True, True, t=0.5))  # dragged into the strip
        self.assertEqual(ccs(out), [], "only a fresh tip press may toggle")

    def test_debounce_swallows_a_bounce(self):
        m = mapper(behaviour__toggle_debounce_ms=200)
        self.assertEqual(ccs(self.press(m, 0.05, 0.0)), [(20, 127)])
        self.lift(m, 0.05, 0.01)
        self.assertEqual(self.press(m, 0.05, 0.05), [], "0.05s < 0.2s debounce")
        self.lift(m, 0.05, 0.3)
        self.assertEqual(ccs(self.press(m, 0.05, 0.4)), [(20, 0)])

    def test_the_pad_never_toggles(self):
        m = mapper()
        self.assertEqual(ccs(m.feed(PenSample(500, 100, True, True, t=0)))[:1][0][0], 16)
        self.assertEqual(m.toggles, [False] * 10)

    def test_leaving_range_arms_the_next_press(self):
        m = mapper()
        self.press(m, 0.05, 0.0)
        m.feed(PenSample(0, 0, False, False, t=0.1))   # pen lifted away
        self.assertEqual(ccs(self.press(m, 0.05, 1.0)), [(20, 0)])

    def test_custom_on_off_values(self):
        m = mapper(midi__button_on=100, midi__button_off=10)
        self.assertEqual(ccs(self.press(m, 0.05, 0.0)), [(20, 100)])
        self.lift(m, 0.05, 0.1)
        self.assertEqual(ccs(self.press(m, 0.05, 1.0)), [(20, 10)])


class PadControllers(unittest.TestCase):
    def test_position_maps_across_the_whole_range(self):
        m = mapper()
        self.assertEqual(ccs(m.feed(PenSample(0, 0, False, True, t=0))), [(16, 0), (17, 0)])
        # y=849 is the last row of the pad: 850 is already the button strip.
        out = m.feed(PenSample(1000, 849, False, True, t=1))
        self.assertEqual(ccs(out), [(16, 127), (17, 127)])

    def test_the_strip_edge_belongs_to_the_strip(self):
        # A press has to register as a button, so the boundary row is a
        # button row. The pad still reaches its full travel just above it.
        m = mapper(layout__strip=0.15)
        self.assertTrue(m.in_strip(0.85))
        self.assertFalse(m.in_strip(0.8499))
        m.feed(PenSample(0, 849, False, True, t=0))
        self.assertEqual(m.state.cc_y_value, 127)

    def test_only_changes_are_sent(self):
        m = mapper()
        m.feed(PenSample(500, 400, False, True, t=0))
        self.assertEqual(m.feed(PenSample(500, 400, False, True, t=1)), [])
        self.assertEqual(m.feed(PenSample(501, 400, False, True, t=2)), [],
                         "a sub-step move must not produce a message")

    def test_frozen_over_the_strip(self):
        m = mapper()
        m.feed(PenSample(500, 400, False, True, t=0))
        self.assertEqual(m.feed(PenSample(200, 950, False, True, t=1)), [])

    def test_not_frozen_when_asked(self):
        m = mapper(behaviour__freeze_xy_in_strip=False)
        m.feed(PenSample(500, 400, False, True, t=0))
        self.assertTrue(m.feed(PenSample(200, 950, False, True, t=1)))

    def test_tip_mode_waits_for_contact(self):
        m = mapper(behaviour__xy_when="tip")
        self.assertEqual(m.feed(PenSample(500, 400, False, True, t=0)), [])
        self.assertTrue(m.feed(PenSample(500, 400, True, True, t=1)))

    def test_out_of_range_sends_nothing(self):
        m = mapper()
        self.assertEqual(m.feed(PenSample(500, 400, False, False, t=0)), [])

    def test_high_resolution_pairs(self):
        m = mapper(midi__high_res=True)
        out = m.feed(PenSample(1000, 0, False, True, t=0))
        self.assertEqual(ccs(out), [(16, 127), (48, 127), (17, 0), (49, 0)])
        mid = mapper(midi__high_res=True)
        pairs = dict(ccs(mid.feed(PenSample(500, 0, False, True, t=0))))
        self.assertEqual(pairs[16] * 128 + pairs[48], 8192, "half of 16383, rounded")

    def test_smoothing_lags_then_settles(self):
        m = mapper(behaviour__smoothing=0.5)
        m.feed(PenSample(0, 0, False, True, t=0))
        m.feed(PenSample(1000, 0, False, True, t=1))
        self.assertEqual(m.state.cc_x_value, 64, "half way after one step")
        for step in range(2, 30):
            m.feed(PenSample(1000, 0, False, True, t=step))
        self.assertEqual(m.state.cc_x_value, 127)

    def test_smoothing_is_dropped_when_the_pen_leaves(self):
        m = mapper(behaviour__smoothing=0.8)
        for step in range(40):
            m.feed(PenSample(0, 0, False, True, t=step))
        m.feed(PenSample(0, 0, False, False, t=41))         # away
        m.feed(PenSample(1000, 0, False, True, t=42))       # back, far away
        self.assertEqual(m.state.cc_x_value, 127,
                         "coming back must not sweep the controller across")


class Housekeeping(unittest.TestCase):
    def test_sync_states_every_button(self):
        m = mapper()
        out = m.sync_messages()
        self.assertEqual(ccs(out), [(20 + i, 0) for i in range(10)])

    def test_set_and_clear_from_outside(self):
        m = mapper()
        self.assertEqual(ccs(m.set_toggle(3, True)), [(23, 127)])
        self.assertEqual(m.set_toggle(3, True), [], "already on")
        self.assertEqual(ccs(m.all_off())[3], (23, 0))
        self.assertEqual(m.toggles, [False] * 10)

    def test_state_tracks_the_pen(self):
        m = mapper()
        m.feed(PenSample(50, 950, True, True, t=0))
        self.assertTrue(m.state.in_strip)
        self.assertEqual(m.state.cell, 0)
        self.assertTrue(m.state.tip)
        m.feed(PenSample(500, 100, False, True, t=1))
        self.assertFalse(m.state.in_strip)
        self.assertIsNone(m.state.cell)


if __name__ == "__main__":
    unittest.main(verbosity=2)
