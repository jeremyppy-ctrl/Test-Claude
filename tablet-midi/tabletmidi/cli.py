"""Command line, for setting the tool up and for running it without a window."""

from __future__ import annotations

import argparse
import sys
import time
from typing import List, Optional

from . import __version__, hidhide
from .config import Config, ConfigError, default_config_path
from .engine import Engine


def attach_console() -> None:
    """Let a windowed executable print into the console that launched it.

    The frozen build has no console of its own, so ``sys.stdout`` is None and
    any print would fail. Borrowing the parent console -- the cmd window the
    user typed into -- makes the subcommands behave normally, and does nothing
    when there is no parent console to borrow.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    import ctypes

    ATTACH_PARENT_PROCESS = -1
    try:
        if not ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            return
    except Exception:
        return
    for name, stream, mode in (
        ("stdout", "CONOUT$", "w"), ("stderr", "CONOUT$", "w"),
        ("stdin", "CONIN$", "r"),
    ):
        try:
            setattr(sys, name, open(stream, mode, buffering=1, encoding="utf-8",
                                    errors="replace"))
        except OSError:
            pass


def _load(args) -> Config:
    try:
        return Config.load_or_default(args.config)
    except (OSError, ConfigError) as exc:
        raise SystemExit("cannot read %s: %s" % (args.config, exc))


def cmd_devices(args) -> int:
    from .hid_win import HidUnavailable, enumerate_devices

    try:
        devices = enumerate_devices(only_pens=not args.all)
    except HidUnavailable as exc:
        print(exc)
        return 1
    if not devices:
        print("No HID device with absolute X/Y was found.")
        print("Pass --all to list every HID collection.")
        return 1
    print("%-5s %s" % ("score", "device"))
    for dev in devices:
        print("%-5d %s" % (dev.score(), dev.describe()))
        print("      %s" % dev.path)
    return 0


def cmd_ports(args) -> int:
    from .midi_win import MidiUnavailable, list_ports

    try:
        ports = list_ports()
    except MidiUnavailable as exc:
        print(exc)
        return 1
    if not ports:
        print("No MIDI output port. Install loopMIDI and create one.")
        return 1
    for port in ports:
        mark = " <- looks like a virtual port" if port.looks_virtual else ""
        print("%2d  %s%s" % (port.index, port.name, mark))
    return 0


def cmd_doctor(args) -> int:
    """Check everything that has to be true before this works."""
    cfg = _load(args)
    problems = 0

    print("Tablet MIDI %s" % __version__)
    print("Configuration: %s" % args.config)
    print()

    print("1. MIDI output port")
    try:
        from .midi_win import find_port, list_ports

        ports = list_ports()
        if not ports:
            print("   FAIL  no MIDI output at all. Install loopMIDI and add a port.")
            problems += 1
        else:
            for port in ports:
                print("   - %s" % port.name)
            exact = find_port(cfg.midi.port_name, fallback=False)
            chosen = exact or find_port(cfg.midi.port_name)
            if exact is None:
                print("   FAIL  nothing matches '%s'." % cfg.midi.port_name)
                problems += 1
                if chosen is not None:
                    print("         '%s' would be used instead." % chosen.name)
            else:
                print("   OK    will send to '%s'" % chosen.name)
            if chosen is not None and not chosen.looks_virtual:
                print("   note  that is not a loopback port; a DAW may not see it.")
    except Exception as exc:
        print("   FAIL  %s" % exc)
        problems += 1

    print()
    print("2. Tablet")
    try:
        from .hid_win import enumerate_devices, pick_device

        devices = enumerate_devices()
        dev = pick_device(
            devices, cfg.device.vid, cfg.device.pid, cfg.device.path,
            cfg.device.name_hint,
        )
        if dev is None:
            print("   FAIL  no tablet found.")
            problems += 1
        else:
            print("   OK    %s" % dev.describe())
            if not dev.readable:
                print("   FAIL  Windows will not let us read it -- hide it with HidHide.")
                problems += 1
            if not dev.has_tip_switch and dev.pressure is None:
                print("   note  no tip switch and no pressure: buttons cannot trigger.")
    except Exception as exc:
        print("   FAIL  %s" % exc)
        problems += 1

    print()
    print("3. Hiding the tablet from Windows")
    state = hidhide.status()
    if not state.installed:
        print("   FAIL  HidHide is not installed -- the pen will still move the cursor.")
        print("         %s" % hidhide.DOWNLOAD_URL)
        problems += 1
    else:
        print("   OK    %s" % state.cli_path)
        exe = hidhide.current_executable()
        print("   %s  allow list contains %s" % ("OK   " if state.allows(exe) else "FAIL ", exe))
        if not state.allows(exe):
            problems += 1
        print("   %s  cloaking is %s" % ("OK   " if state.cloaking else "FAIL ", "on" if state.cloaking else "off"))
        if not state.cloaking:
            problems += 1
        if state.hidden:
            for entry in state.hidden:
                print("         hidden: %s" % entry)
        else:
            print("   FAIL  no device is hidden.")
            problems += 1

    print()
    print("%d problem(s)." % problems if problems else "Everything checks out.")
    return 1 if problems else 0


def _describe(snap, cfg: Config) -> str:
    pen = snap.pen
    strip = "strip" if pen.in_strip else "pad  "
    cell = "" if pen.cell is None else " cell %2d" % (pen.cell + 1)
    toggles = "".join("#" if t else "." for t in snap.toggles)
    return (
        "%s %s x=%.3f y=%.3f %s%s  CC%d=%3d CC%d=%3d  [%s]  %d msg"
        % (
            "IN " if pen.in_range else "OUT",
            "TIP" if pen.tip else "   ",
            pen.nx, pen.ny, strip, cell,
            cfg.midi.cc_x, pen.cc_x_value,
            cfg.midi.cc_y, pen.cc_y_value,
            toggles, snap.messages,
        )
    )


def cmd_monitor(args) -> int:
    """Live readout, without sending anything anywhere."""
    cfg = _load(args)
    engine = Engine(cfg, log=lambda m: print("  " + m), simulate=args.simulate,
                    midi_enabled=False)
    engine.start()
    print("Move the pen. Ctrl-C to stop.")
    try:
        while True:
            time.sleep(0.08)
            snap = engine.snapshot()
            sys.stdout.write("\r" + _describe(snap, cfg).ljust(110))
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        print()
    return 0


def cmd_run(args) -> int:
    cfg = _load(args)
    engine = Engine(cfg, log=lambda m: print(m), simulate=args.simulate)
    engine.start()
    print("Running. Ctrl-C to stop.")
    try:
        while True:
            time.sleep(0.1)
            if args.verbose:
                snap = engine.snapshot()
                sys.stdout.write("\r" + _describe(snap, cfg).ljust(110))
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        print()
    return 0


def cmd_calibrate(args) -> int:
    """Record the rectangle of the tablet you actually want to use."""
    cfg = _load(args)
    engine = Engine(cfg, log=lambda m: print("  " + m), simulate=args.simulate,
                    midi_enabled=False)
    engine.start()
    time.sleep(0.6)
    snap = engine.snapshot()
    if snap.error:
        engine.stop()
        print(snap.error)
        return 1

    engine.begin_calibration()
    print("Sweep the pen over the whole area you want to use, corner to corner.")
    print("Press Enter when done.")
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        engine.end_calibration(keep=False)
        engine.stop()
        return 1
    ok = engine.end_calibration(keep=True)
    engine.stop()
    if not ok:
        print("Nothing recorded.")
        return 1
    engine.cfg.save(args.config)
    print("Saved to %s" % args.config)
    return 0


def cmd_hidhide(args) -> int:
    cfg = _load(args)
    state = hidhide.status()
    if args.action == "status":
        print("installed: %s" % state.installed)
        if state.installed:
            print("cli: %s" % state.cli_path)
            print("administrator: %s" % state.elevated)
            print("cloaking: %s" % state.cloaking)
            print("this program: %s" % hidhide.current_executable())
            print("allow-listed: %s" % state.allows(hidhide.current_executable()))
            for entry in state.hidden:
                print("hidden: %s" % entry)
        else:
            print(hidhide.DOWNLOAD_URL)
        return 0 if state.installed else 1

    from .hid_win import enumerate_devices, pick_device

    dev = pick_device(
        enumerate_devices(), cfg.device.vid, cfg.device.pid, cfg.device.path,
        cfg.device.name_hint,
    )
    if dev is None:
        print("No tablet found; nothing to do.")
        return 1
    print("Tablet: %s" % dev.describe())

    try:
        paths = hidhide.device_paths_for(dev.vid, dev.pid) or (
            [dev.instance_id] if dev.instance_id else []
        )
    except hidhide.HidHideError as exc:
        print(exc)
        return 1
    if not paths:
        print("HidHide does not list this device.")
        return 1

    exe = hidhide.current_executable()
    steps = (
        hidhide.plan_install(paths, exe) if args.action == "install"
        else hidhide.plan_remove(paths, exe)
    )
    dry = not args.yes
    if dry:
        print("\nThese commands would run (pass --yes to do it):\n")
    try:
        ok = hidhide.apply(steps, dry_run=dry, log=print)
    except hidhide.HidHideError as exc:
        print(exc)
        return 1
    if not dry:
        print("Unplug and replug the tablet for the change to take effect.")
    return 0 if ok else 1


def cmd_config(args) -> int:
    if args.action == "path":
        print(args.config)
        return 0
    cfg = _load(args)
    if args.action == "init":
        cfg.save(args.config)
        print("Wrote %s" % args.config)
        return 0
    import json

    print(json.dumps(cfg.to_dict(), indent=2))
    return 0


def cmd_gui(args) -> int:
    from .gui import main as gui_main

    extra = ["--config", args.config]
    if args.simulate:
        extra.append("--simulate")
    return gui_main(extra)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tabletmidi",
        description="Turn a graphics tablet into a virtual MIDI controller.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--config", default=default_config_path(), help="configuration file to use"
    )
    parser.add_argument(
        "--simulate", action="store_true",
        help="generate a fake pen instead of reading the tablet",
    )
    sub = parser.add_subparsers(dest="command")

    gui = sub.add_parser("gui", help="open the window (the default)")
    gui.set_defaults(func=cmd_gui)

    devices = sub.add_parser("devices", help="list tablets Windows can see")
    devices.add_argument("--all", action="store_true", help="every HID collection")
    devices.set_defaults(func=cmd_devices)

    sub.add_parser("ports", help="list MIDI output ports").set_defaults(func=cmd_ports)
    sub.add_parser("doctor", help="check that everything is ready").set_defaults(
        func=cmd_doctor
    )
    sub.add_parser("monitor", help="live readout, sends nothing").set_defaults(
        func=cmd_monitor
    )
    sub.add_parser("calibrate", help="record the area you want to use").set_defaults(
        func=cmd_calibrate
    )

    run = sub.add_parser("run", help="run headless")
    run.add_argument("-v", "--verbose", action="store_true")
    run.set_defaults(func=cmd_run)

    hh = sub.add_parser("hidhide", help="hide the tablet from Windows")
    hh.add_argument("action", choices=("status", "install", "remove"))
    hh.add_argument("--yes", action="store_true", help="actually run the commands")
    hh.set_defaults(func=cmd_hidhide)

    conf = sub.add_parser("config", help="inspect or create the configuration")
    conf.add_argument("action", choices=("show", "init", "path"))
    conf.set_defaults(func=cmd_config)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    # Only the window is silent; every other command talks to a console.
    if any(not arg.startswith("-") and arg != "gui" for arg in raw):
        attach_console()
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        args.func = cmd_gui
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
