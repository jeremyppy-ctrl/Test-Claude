"""The Windows structures must match the SDK byte for byte.

These run on any platform: every field is declared with an explicit width, so
a mistake shows up here rather than as a mysterious failure on the tablet.
"""

import os
import sys
import unittest
from ctypes import sizeof

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tabletmidi import hid_win, midi_win


class Sizes(unittest.TestCase):
    """Sizes taken from hidpi.h, setupapi.h, minwinbase.h and mmeapi.h."""

    def test_hid_structures(self):
        self.assertEqual(sizeof(hid_win.HIDD_ATTRIBUTES), 12)
        self.assertEqual(sizeof(hid_win.HIDP_CAPS), 64)
        self.assertEqual(sizeof(hid_win.HIDP_VALUE_CAPS), 72)
        self.assertEqual(sizeof(hid_win.HIDP_BUTTON_CAPS), 72)

    def test_setupapi_structures_on_64_bit(self):
        self.assertEqual(sizeof(hid_win.SP_DEVICE_INTERFACE_DATA), 32)
        self.assertEqual(sizeof(hid_win.SP_DEVINFO_DATA), 32)
        self.assertEqual(sizeof(hid_win.OVERLAPPED), 32)

    def test_midi_caps_is_84_bytes(self):
        # Wide characters are 2 bytes on Windows but 4 elsewhere, so szPname
        # is declared as raw UTF-16 units to keep this true everywhere.
        self.assertEqual(sizeof(midi_win.MIDIOUTCAPSW), 84)

    def test_port_name_decodes_from_utf16(self):
        caps = midi_win.MIDIOUTCAPSW()
        for index, char in enumerate("loopMIDI Port"):
            caps.szPname[index] = ord(char)
        self.assertEqual(caps.name, "loopMIDI Port")

    def test_empty_port_name(self):
        self.assertEqual(midi_win.MIDIOUTCAPSW().name, "")


class StatusCodes(unittest.TestCase):
    def test_hidp_status_values(self):
        self.assertEqual(hid_win.HIDP_STATUS_SUCCESS, 0x00110000)
        self.assertEqual(hid_win.HIDP_STATUS_USAGE_NOT_FOUND & 0xFFFFFFFF, 0xC0110004)
        self.assertEqual(
            hid_win.HIDP_STATUS_INCOMPATIBLE_REPORT_ID & 0xFFFFFFFF, 0xC011000A
        )


class Ranking(unittest.TestCase):
    """The tablet exposes several collections; we must pick the pen."""

    def pen(self, **kwargs):
        info = hid_win.DeviceInfo(path=kwargs.pop("path", r"\\?\hid#x"))
        info.x = hid_win.AxisInfo(1, 0x30, 0, kwargs.pop("x_max", 32767), 16)
        info.y = hid_win.AxisInfo(1, 0x31, 0, kwargs.pop("y_max", 32767), 16)
        for key, value in kwargs.items():
            setattr(info, key, value)
        return info

    def test_a_collection_without_axes_is_not_a_candidate(self):
        self.assertEqual(hid_win.DeviceInfo(path="x").score(), -1)

    def test_the_digitizer_outranks_the_mouse_collection(self):
        mouse = self.pen(usage_page=0x01, usage=0x02, x_max=1023, readable=True)
        digitizer = self.pen(
            usage_page=0x0D, usage=0x02, readable=True,
            buttons=[(0x0D, 0x42), (0x0D, 0x32)],
        )
        self.assertGreater(digitizer.score(), mouse.score())

    def test_pick_prefers_the_best_and_honours_a_pinned_path(self):
        mouse = self.pen(path=r"\\?\hid#mouse", usage_page=0x01, x_max=1023)
        digitizer = self.pen(
            path=r"\\?\hid#pen", usage_page=0x0D, buttons=[(0x0D, 0x42)]
        )
        devices = [mouse, digitizer]
        self.assertIs(hid_win.pick_device(devices), digitizer)
        self.assertIs(
            hid_win.pick_device(devices, path=r"\\?\HID#MOUSE"), mouse,
            "a pinned path wins, and matches case-insensitively",
        )

    def test_pick_filters_by_vendor_and_name(self):
        a = self.pen(path="a", vid=0x256C, pid=0x006D, product="Tablet A")
        b = self.pen(path="b", vid=0x1234, pid=0x5678, product="Other")
        self.assertIs(hid_win.pick_device([a, b], vid=0x256C), a)
        self.assertIs(hid_win.pick_device([a, b], name_hint="other"), b)
        self.assertIsNone(hid_win.pick_device([a, b], vid=0xFFFF))

    def test_a_name_hint_that_matches_nothing_does_not_empty_the_list(self):
        a = self.pen(path="a", product="Tablet A")
        self.assertIs(hid_win.pick_device([a], name_hint="nonesuch"), a)

    def test_flags_read_off_the_button_list(self):
        info = self.pen(buttons=[(0x0D, 0x42), (0x0D, 0x32)])
        self.assertTrue(info.has_tip_switch)
        self.assertTrue(info.has_in_range)
        self.assertIn("tip", info.describe())


class Grouping(unittest.TestCase):
    """A tablet is several HID collections but one thing to hide."""

    def collection(self, vid, pid, **kwargs):
        info = hid_win.DeviceInfo(path=kwargs.pop("path", "p"), vid=vid, pid=pid)
        if kwargs.pop("pen", False):
            info.x = hid_win.AxisInfo(1, 0x30, 0, kwargs.pop("x_max", 32767), 16)
            info.y = hid_win.AxisInfo(1, 0x31, 0, 32767, 16)
        for key, value in kwargs.items():
            setattr(info, key, value)
        return info

    def test_collections_of_one_device_collapse_to_one_row(self):
        rows = hid_win.group_by_device([
            self.collection(0x256C, 0x006D, path="a", pen=True, usage_page=0x0D,
                            buttons=[(0x0D, 0x42)]),
            self.collection(0x256C, 0x006D, path="b", pen=True, x_max=1023),
            self.collection(0x256C, 0x006D, path="c"),
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].collections, 3)
        self.assertEqual(rows[0].path, "a", "the best collection represents it")

    def test_a_device_with_no_pen_is_still_offered(self):
        # This is the tablet that has not been woken out of mouse mode yet --
        # refusing to list it would leave no way to hide it.
        rows = hid_win.group_by_device([self.collection(0x256C, 0x006D)])
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].has_pen)

    def test_pens_sort_ahead_of_everything_else(self):
        rows = hid_win.group_by_device([
            self.collection(0x046D, 0xC52B, path="mouse"),
            self.collection(0x256C, 0x006D, path="pen", pen=True,
                            buttons=[(0x0D, 0x42)]),
        ])
        self.assertEqual([d.path for d in rows], ["pen", "mouse"])

    def test_devices_without_a_vendor_id_are_dropped(self):
        self.assertEqual(hid_win.group_by_device([self.collection(0, 0)]), [])

    def test_distinct_devices_stay_distinct(self):
        rows = hid_win.group_by_device([
            self.collection(0x256C, 0x006D), self.collection(0x256C, 0x0064),
        ])
        self.assertEqual(len(rows), 2)


class AxisRange(unittest.TestCase):
    """LogicalMax comes back signed, and sometimes not at all."""

    def test_a_plain_maximum_is_kept(self):
        self.assertEqual(hid_win.logical_maximum(32767, 16), 32767)
        self.assertEqual(hid_win.logical_maximum(4095, 16), 4095)

    def test_a_full_16_bit_range_arrives_as_minus_one(self):
        # 65535 does not fit a signed 32-bit LogicalMax the way Windows
        # fills it in, so the tablet reports -1 for a full-range axis.
        self.assertEqual(hid_win.logical_maximum(-1, 16), 65535)
        self.assertEqual(hid_win.logical_maximum(-1, 8), 255)

    def test_a_missing_maximum_becomes_the_widest_the_field_holds(self):
        self.assertEqual(hid_win.logical_maximum(0, 16), 65535)

    def test_a_nonsense_bit_size_is_left_alone(self):
        self.assertEqual(hid_win.logical_maximum(1234, 0), 1234)
        self.assertEqual(hid_win.logical_maximum(1234, 99), 1234)

    def test_such_an_axis_still_drives_the_full_controller_range(self):
        from tabletmidi.config import Config
        from tabletmidi.mapping import Mapper, PenSample

        cfg = Config()
        cfg.behaviour.smoothing = 0.0
        limit = hid_win.logical_maximum(-1, 16)
        mapper = Mapper(cfg, limit, limit)
        mapper.feed(PenSample(limit, 0, False, True, t=0.0))
        self.assertEqual(mapper.state.cc_x_value, 127,
                         "a full-range axis must reach the top of the CC")


class PortSelection(unittest.TestCase):
    """Choosing a MIDI port by a name winmm may have truncated."""

    PORTS = [
        midi_win.MidiPort(0, "Microsoft GS Wavetable Synth"),
        midi_win.MidiPort(1, "loopMIDI Port"),
        midi_win.MidiPort(2, "Some USB Keyboard"),
    ]

    def setUp(self):
        self._real = midi_win.list_ports
        midi_win.list_ports = lambda: list(self.PORTS)

    def tearDown(self):
        midi_win.list_ports = self._real

    def test_exact_prefix_and_substring_all_match(self):
        for name in ("loopMIDI Port", "loopMIDI", "midi port"):
            self.assertEqual(midi_win.find_port(name).index, 1, name)

    def test_an_empty_name_prefers_a_loopback_port(self):
        self.assertEqual(midi_win.find_port("").index, 1)

    def test_a_missing_name_is_reported_when_asked(self):
        self.assertIsNone(midi_win.find_port("nonesuch", fallback=False))

    def test_a_missing_name_substitutes_when_allowed(self):
        self.assertEqual(midi_win.find_port("nonesuch").index, 1)

    def test_the_wavetable_synth_is_the_last_resort(self):
        midi_win.list_ports = lambda: [self.PORTS[0], self.PORTS[2]]
        self.assertEqual(midi_win.find_port("").index, 2)
        midi_win.list_ports = lambda: [self.PORTS[0]]
        self.assertIsNone(midi_win.find_port(""), "a synth is nowhere to send")

    def test_no_ports_at_all(self):
        midi_win.list_ports = lambda: []
        self.assertIsNone(midi_win.find_port("loopMIDI"))


class PlatformGuards(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "only meaningful off Windows")
    def test_modules_import_but_refuse_to_run(self):
        with self.assertRaises(hid_win.HidUnavailable):
            hid_win.enumerate_devices()
        with self.assertRaises(midi_win.MidiUnavailable):
            midi_win.list_ports()


if __name__ == "__main__":
    unittest.main(verbosity=2)
