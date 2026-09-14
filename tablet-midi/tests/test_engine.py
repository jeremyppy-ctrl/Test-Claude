"""The worker loop, driven by a scripted reader instead of a tablet."""

import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tabletmidi.config import Config
from tabletmidi.engine import Engine, NullMidiOut, Reader, SimulatedReader
from tabletmidi.mapping import PenSample


class ScriptedReader(Reader):
    """Replays a list of samples, then hovers at the last one."""

    label = "scripted"
    x_limit = 1000
    y_limit = 1000

    def __init__(self, samples):
        self.samples = list(samples)
        self.served = 0
        self.closed = False
        self.drained = threading.Event()

    def sample(self, t, timeout_ms=20):
        time.sleep(0.001)
        if self.samples:
            self.served += 1
            return self.samples.pop(0)
        self.drained.set()
        return None

    def close(self):
        self.closed = True


class FailingReader(Reader):
    label = "flaky"
    x_limit = y_limit = 1000

    def __init__(self):
        self.opened = 0

    def sample(self, t, timeout_ms=20):
        time.sleep(0.001)
        raise OSError("tablet unplugged")


class Recorder(NullMidiOut):
    def __init__(self):
        self.messages = []

    def send(self, msg):
        self.messages.append((msg.data1, msg.data2))

    def send_all(self, messages):
        for msg in messages:
            self.send(msg)


def engine_with(reader, cfg=None):
    cfg = cfg or Config()
    cfg.behaviour.smoothing = 0.0
    engine = Engine(cfg, simulate=True, midi_enabled=False)
    engine._reader_override = reader
    engine._open_reader = lambda: _attach(engine, reader)
    return engine


def _attach(engine, reader):
    engine._reader = reader
    engine.mapper.x_limit = reader.x_limit
    engine.mapper.y_limit = reader.y_limit
    engine._set(device=reader.label, error="")
    return True


class Lifecycle(unittest.TestCase):
    def test_start_and_stop_are_clean(self):
        reader = ScriptedReader([])
        engine = engine_with(reader)
        engine.start()
        self.assertTrue(engine.running)
        engine.stop()
        self.assertFalse(engine.running)
        self.assertTrue(reader.closed, "the tablet must be released on stop")

    def test_starting_twice_keeps_one_thread(self):
        engine = engine_with(ScriptedReader([]))
        engine.start()
        first = engine._thread
        engine.start()
        self.assertIs(engine._thread, first)
        engine.stop()

    def test_stop_without_start_is_harmless(self):
        engine_with(ScriptedReader([])).stop()


class Processing(unittest.TestCase):
    def run_samples(self, samples, cfg=None):
        reader = ScriptedReader(samples)
        engine = engine_with(reader, cfg)
        recorder = Recorder()
        engine._midi = recorder
        engine._open_midi = lambda: True
        engine.start()
        reader.drained.wait(3.0)
        time.sleep(0.05)
        engine.stop()
        return engine, recorder

    def test_a_press_in_the_strip_toggles_and_is_sent(self):
        engine, recorder = self.run_samples([
            PenSample(50, 950, False, True, t=0.0),
            PenSample(50, 950, True, True, t=0.1),
        ])
        self.assertIn((20, 127), recorder.messages)
        self.assertTrue(engine.snapshot().toggles[0])

    def test_sync_announces_every_button_first(self):
        _, recorder = self.run_samples([])
        self.assertEqual(recorder.messages[:10], [(20 + i, 0) for i in range(10)])

    def test_snapshot_reports_progress(self):
        engine, _ = self.run_samples([
            PenSample(500, 400, False, True, t=0.0),
            PenSample(600, 400, False, True, t=0.1),
        ])
        snap = engine.snapshot()
        self.assertEqual(snap.samples, 2)
        self.assertGreater(snap.messages, 0)
        self.assertEqual(snap.x_limit, 1000)

    def test_a_disconnect_is_survived_and_reported(self):
        engine = engine_with(FailingReader())
        engine._midi = Recorder()
        engine._open_midi = lambda: True
        engine.start()
        time.sleep(0.2)
        snap = engine.snapshot()
        engine.stop()
        self.assertIn("unplugged", snap.error)
        self.assertFalse(engine.running)


class Actions(unittest.TestCase):
    def setUp(self):
        self.reader = ScriptedReader([PenSample(500, 400, False, True, t=0.0)] * 200)
        self.engine = engine_with(self.reader)
        self.recorder = Recorder()
        self.engine._midi = self.recorder
        self.engine._open_midi = lambda: True
        self.engine.start()
        time.sleep(0.05)

    def tearDown(self):
        self.engine.stop()

    def wait(self, predicate, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def test_toggle_from_outside_the_thread(self):
        self.engine.toggle(4, True)
        self.assertTrue(self.wait(lambda: self.engine.snapshot().toggles[4]))
        self.assertIn((24, 127), self.recorder.messages)

    def test_all_off_clears_everything(self):
        self.engine.toggle(2, True)
        self.assertTrue(self.wait(lambda: self.engine.snapshot().toggles[2]))
        self.engine.all_off()
        self.assertTrue(self.wait(lambda: not any(self.engine.snapshot().toggles)))

    def test_out_of_range_index_is_ignored(self):
        self.engine.toggle(99, True)
        time.sleep(0.05)
        self.assertEqual(len(self.engine.snapshot().toggles), 10)

    def test_calibration_records_the_swept_box(self):
        self.engine.begin_calibration()
        self.assertTrue(self.wait(lambda: self.engine.snapshot().calibrating))
        self.engine.post(lambda: self.engine._cal.__setitem__(0, 120.0))
        self.engine.post(lambda: self.engine._cal.__setitem__(1, 880.0))
        self.engine.post(lambda: self.engine._cal.__setitem__(2, 60.0))
        self.engine.post(lambda: self.engine._cal.__setitem__(3, 940.0))
        time.sleep(0.05)
        self.assertTrue(self.engine.end_calibration(keep=True))
        self.assertEqual(self.engine.cfg.area.x_min, 120)
        self.assertEqual(self.engine.cfg.area.x_max, 880)
        self.assertEqual(self.engine.cfg.area.y_max, 940)

    def test_a_flat_sweep_is_refused(self):
        # One axis with no extent would divide by zero later on.
        self.engine.begin_calibration()
        self.assertTrue(self.wait(lambda: self.engine.snapshot().calibrating))
        time.sleep(0.05)
        self.assertFalse(
            self.engine.end_calibration(keep=True),
            "a sweep that never moved must not be stored",
        )

    def test_calibration_can_be_thrown_away(self):
        before = self.engine.cfg.area.x_max
        self.engine.begin_calibration()
        time.sleep(0.05)
        self.engine.end_calibration(keep=False)
        self.assertEqual(self.engine.cfg.area.x_max, before)

    def test_applying_a_new_layout_keeps_the_buttons_that_remain(self):
        self.engine.toggle(1, True)
        self.assertTrue(self.wait(lambda: self.engine.snapshot().toggles[1]))
        cfg = Config()
        cfg.layout.buttons = 4
        self.engine.apply_config(cfg)
        self.assertTrue(self.wait(lambda: len(self.engine.snapshot().toggles) == 4))
        self.assertTrue(self.engine.snapshot().toggles[1], "toggle 1 survived")


class Simulation(unittest.TestCase):
    def test_the_simulated_pen_stays_inside_the_tablet(self):
        now = [0.0]

        def clock():
            now[0] += 0.05
            return now[0]

        reader = SimulatedReader(clock=clock, sleep=lambda _s: None)
        for _ in range(400):
            sample = reader.sample(0.0, timeout_ms=1)
            self.assertTrue(0 <= sample.x <= reader.x_limit)
            self.assertTrue(0 <= sample.y <= reader.y_limit)

    def test_it_eventually_presses_the_strip(self):
        now = [0.0]

        def clock():
            now[0] += 0.02
            return now[0]

        reader = SimulatedReader(clock=clock, sleep=lambda _s: None)
        samples = [reader.sample(0.0, timeout_ms=1) for _ in range(400)]
        tips = [s for s in samples if s.tip]
        self.assertTrue(tips, "the simulation must exercise the buttons")
        for sample in tips:
            self.assertGreater(
                sample.y / reader.y_limit, 0.85, "taps must land in the strip"
            )
        cells = {int(s.x / reader.x_limit * 10) for s in tips}
        self.assertGreater(len(cells), 1, "it should move between buttons")


if __name__ == "__main__":
    unittest.main(verbosity=2)
