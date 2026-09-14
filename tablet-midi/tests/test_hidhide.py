"""Reading HidHideCLI output, which differs between its versions."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tabletmidi import hidhide

JSON_OUTPUT = r"""
[
  {
    "friendlyName": "Medion Graphics Tablet",
    "devices": [
      {"deviceInstancePath": "HID\\VID_256C&PID_006D\\7&2A1B&0&0000",
       "symbolicLink": "\\\\?\\hid#vid_256c&pid_006d#7&2a1b&0&0000",
       "present": true},
      {"deviceInstancePath": "HID\\VID_256C&PID_006D\\7&2A1B&0&0001",
       "present": true}
    ]
  },
  {
    "friendlyName": "USB Receiver",
    "devices": [{"deviceInstancePath": "HID\\VID_046D&PID_C52B\\6&1&0", "present": true}]
  }
]
"""

PLAIN_OUTPUT = """
HID\\VID_256C&PID_006D\\7&2A1B&0&0000
HID\\VID_256C&PID_006D\\7&2A1B&0&0001
HID\\VID_046D&PID_C52B\\6&1&0
"""


class ParsingDevices(unittest.TestCase):
    def test_json(self):
        found = hidhide.parse_devices(JSON_OUTPUT)
        self.assertEqual(len(found), 3)
        self.assertIn(r"HID\VID_256C&PID_006D\7&2A1B&0&0000", found)

    def test_plain_lines(self):
        self.assertEqual(len(hidhide.parse_devices(PLAIN_OUTPUT)), 3)

    def test_noise_is_dropped(self):
        self.assertEqual(hidhide.parse_devices("no devices found\n\n"), [])
        self.assertEqual(hidhide.parse_devices(""), [])

    def test_duplicates_collapse(self):
        doubled = PLAIN_OUTPUT + PLAIN_OUTPUT
        self.assertEqual(len(hidhide.parse_devices(doubled)), 3)

    def test_broken_json_falls_back_to_lines(self):
        broken = "[{\"deviceInstancePath\": \"HID\\\\VID_256C&PID_006D\\\\A\""
        self.assertEqual(len(hidhide.parse_devices(broken)), 1)


class ParsingApps(unittest.TestCase):
    def test_json_and_plain(self):
        self.assertEqual(
            hidhide.parse_apps('[{"path": "C:\\\\Tools\\\\TabletMidi.exe"}]'),
            [r"C:\Tools\TabletMidi.exe"],
        )
        self.assertEqual(
            hidhide.parse_apps("C:\\Python\\python.exe\nnot a path\n"),
            [r"C:\Python\python.exe"],
        )


class Matching(unittest.TestCase):
    def test_vendor_and_product_are_matched_case_insensitively(self):
        entry = r"hid\vid_256c&pid_006d\7&2a1b&0&0000"
        self.assertTrue(hidhide._matches(entry, 0x256C, 0x006D))
        self.assertFalse(hidhide._matches(entry, 0x256C, 0x0001))

    def test_status_reports_what_it_hides(self):
        state = hidhide.Status(hidden=hidhide.parse_devices(PLAIN_OUTPUT))
        self.assertTrue(state.hides(0x256C, 0x006D))
        self.assertFalse(state.hides(0xDEAD, 0xBEEF))

    def test_allow_list_comparison_ignores_case_and_separators(self):
        state = hidhide.Status(allowed=[r"C:\Tools\TabletMidi.exe"])
        self.assertTrue(state.allows(r"c:\tools\tabletmidi.exe"))
        self.assertFalse(state.allows(r"C:\Other\TabletMidi.exe"))


class Plans(unittest.TestCase):
    PATHS = [r"HID\VID_256C&PID_006D\A", r"HID\VID_256C&PID_006D\B"]
    EXE = r"C:\Tools\TabletMidi.exe"

    def test_install_allows_the_app_before_hiding_anything(self):
        steps = hidhide.plan_install(self.PATHS, self.EXE)
        flags = [step.args[0] for step in steps]
        self.assertEqual(flags[0], "--app-reg")
        self.assertEqual(flags.count("--dev-hide"), 2)
        self.assertEqual(flags[-1], "--cloak-on")
        self.assertLess(
            flags.index("--app-reg"), flags.index("--cloak-on"),
            "hiding before allowing would lock us out of our own tablet",
        )

    def test_the_inverse_flag_is_optional(self):
        steps = hidhide.plan_install(self.PATHS, self.EXE)
        optional = [step for step in steps if step.optional]
        self.assertEqual([step.args[0] for step in optional], ["--inv-off"])

    def test_remove_undoes_install(self):
        steps = hidhide.plan_remove(self.PATHS, self.EXE)
        flags = [step.args[0] for step in steps]
        self.assertEqual(flags.count("--dev-unhide"), 2)
        self.assertIn("--app-unreg", flags)

    def test_a_dry_run_executes_nothing(self):
        lines = []
        hidhide.apply(
            hidhide.plan_install(self.PATHS, self.EXE), dry_run=True, log=lines.append
        )
        self.assertEqual(len(lines), 5, "app-reg, inv-off, two dev-hide, cloak-on")
        self.assertTrue(all(line.startswith("would run:") for line in lines))

    def test_applying_for_real_without_rights_is_refused(self):
        if hidhide.is_elevated():
            self.skipTest("running elevated")
        with self.assertRaises(hidhide.HidHideError):
            hidhide.apply(hidhide.plan_install(self.PATHS, self.EXE), dry_run=False)

    def test_steps_render_with_quoting(self):
        step = hidhide.Step(["--app-reg", r"C:\Program Files\x.exe"], "why")
        self.assertEqual(str(step), '--app-reg "C:\\Program Files\\x.exe"')


class Discovery(unittest.TestCase):
    def test_no_cli_off_windows(self):
        if sys.platform == "win32":
            self.skipTest("Windows may genuinely have HidHide")
        self.assertIsNone(hidhide.find_cli())
        self.assertFalse(hidhide.is_elevated())

    def test_running_without_the_cli_explains_itself(self):
        if hidhide.find_cli():
            self.skipTest("HidHide is installed here")
        with self.assertRaises(hidhide.HidHideError) as caught:
            hidhide.run_cli(["--dev-all"])
        self.assertIn("not installed", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
