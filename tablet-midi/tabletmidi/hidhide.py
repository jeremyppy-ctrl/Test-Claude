"""Driving HidHide, so Windows stops seeing the tablet at all.

HidHide is a filter driver that hides HID devices from every application
except the ones on its allow list. Pointing it at the tablet and allowing this
program is what stops the cursor from moving: Windows never receives the pen
reports in the first place, so there is nothing left to suppress higher up.

Everything here is reversible -- :func:`plan_remove` undoes :func:`plan_install`.
"""

from __future__ import annotations

import ctypes
import glob
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Optional

DOWNLOAD_URL = "https://github.com/nefarius/HidHide/releases"

# HidHide has moved its CLI between releases -- sometimes under an x64
# subfolder, sometimes directly in the install directory, and the vendor
# folder has been spelled several ways. Search widely, but stay inside the
# vendor's own directories so this never walks all of Program Files.
_CLI_NAME = "HidHideCLI.exe"
_CLI_GLOBS = (
    r"C:\Program Files\Nefarius Software Solutions*\HidHide\x64\HidHideCLI.exe",
    r"C:\Program Files\Nefarius Software Solutions*\HidHide\x86\HidHideCLI.exe",
    r"C:\Program Files\Nefarius Software Solutions*\HidHide\HidHideCLI.exe",
    r"C:\Program Files\Nefarius*\**\HidHideCLI.exe",
    r"C:\Program Files (x86)\Nefarius*\**\HidHideCLI.exe",
)


class HidHideError(RuntimeError):
    pass


@dataclass
class Step:
    """One CLI invocation, shown to the user before anything runs."""

    args: List[str]
    why: str
    #: A step that may legitimately fail on older HidHide builds.
    optional: bool = False

    def __str__(self) -> str:
        return " ".join(('"%s"' % a if " " in a else a) for a in self.args)


@dataclass
class Status:
    installed: bool = False
    #: The filter driver is present even when the CLI cannot be located.
    driver_present: bool = False
    cli_path: str = ""
    elevated: bool = False
    cloaking: bool = False
    hidden: List[str] = field(default_factory=list)
    allowed: List[str] = field(default_factory=list)
    error: str = ""

    def hides(self, vid: int, pid: int) -> bool:
        return any(_matches(entry, vid, pid) for entry in self.hidden)

    def allows(self, exe: str) -> bool:
        target = _normalise_exe(exe)
        return any(_normalise_exe(entry) == target for entry in self.allowed)


def _normalise_exe(path: str) -> str:
    """A Windows image path, folded for comparison.

    Windows paths are case-insensitive and accept either slash, and these
    strings come from HidHide rather than from the local filesystem, so they
    are folded by Windows rules whatever host is running the comparison.
    """
    return (path or "").strip().strip('"').replace("/", "\\").rstrip("\\").lower()


def _registry_install_locations() -> List[str]:
    """Where the uninstall entries say HidHide put itself."""
    if sys.platform != "win32":
        return []
    import winreg

    found: List[str] = []
    roots = (
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for root, subkey in roots:
        try:
            parent = winreg.OpenKey(root, subkey)
        except OSError:
            continue
        with parent:
            try:
                count = winreg.QueryInfoKey(parent)[0]
            except OSError:
                continue
            for index in range(count):
                try:
                    with winreg.OpenKey(parent, winreg.EnumKey(parent, index)) as entry:
                        name = _reg_value(entry, "DisplayName")
                        if "hidhide" not in (name or "").lower():
                            continue
                        location = _reg_value(entry, "InstallLocation")
                        if location:
                            found.append(location)
                except OSError:
                    continue
    return found


def _reg_value(key, name: str) -> str:
    import winreg

    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return value if isinstance(value, str) else ""


def driver_present() -> bool:
    """True when the HidHide filter driver is installed, CLI or not."""
    if sys.platform != "win32":
        return False
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.exists(os.path.join(root, "System32", "drivers", "HidHide.sys"))


def find_cli() -> Optional[str]:
    """Locate HidHideCLI.exe, or None when it cannot be found."""
    if sys.platform != "win32":
        return None
    override = os.environ.get("HIDHIDE_CLI")
    if override and os.path.exists(override):
        return override
    for pattern in _CLI_GLOBS:
        for hit in sorted(glob.glob(pattern, recursive=True), reverse=True):
            if os.path.exists(hit):
                return hit
    # The globs assume the default drive; the registry knows the truth.
    for location in _registry_install_locations():
        direct = os.path.join(location, _CLI_NAME)
        if os.path.exists(direct):
            return direct
        for hit in sorted(
            glob.glob(os.path.join(location, "**", _CLI_NAME), recursive=True),
            reverse=True,
        ):
            return hit
    return None


def is_elevated() -> bool:
    """True when the process can modify the HidHide configuration."""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def current_executable() -> str:
    """The image path to put on the allow list.

    Frozen into an .exe this is the program itself; run from source it is the
    Python interpreter, which allows any script it runs to see the tablet.
    """
    return os.path.abspath(sys.executable)


def run_cli(args: List[str], cli: Optional[str] = None, timeout: int = 30):
    """Run HidHideCLI and hand back (returncode, stdout+stderr)."""
    cli = cli or find_cli()
    if not cli:
        raise HidHideError(
            "HidHide is not installed. Get it from " + DOWNLOAD_URL
        )
    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            [cli] + args, capture_output=True, text=True, timeout=timeout,
            startupinfo=startupinfo, creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        raise HidHideError("HidHideCLI did not answer within %ds" % timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _walk_json(node, tiers) -> None:
    """Collect device strings, most specific key first.

    A HidHide entry usually carries both ``deviceInstancePath`` and
    ``symbolicLink``, and only the former is what ``--dev-hide`` accepts, so
    the two must not be mixed together.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            low = key.lower()
            if isinstance(value, str) and _looks_like_device(value):
                if "instancepath" in low:
                    tiers[0].append(value)
                elif "path" in low:
                    tiers[1].append(value)
                else:
                    tiers[2].append(value)
            else:
                _walk_json(value, tiers)
    elif isinstance(node, list):
        for item in node:
            _walk_json(item, tiers)
    elif isinstance(node, str) and _looks_like_device(node):
        tiers[2].append(node)


def _looks_like_device(text: str) -> bool:
    upper = text.upper()
    return "VID_" in upper and "\\" in text


def parse_devices(text: str) -> List[str]:
    """Device instance paths out of HidHideCLI output, JSON or plain."""
    text = (text or "").strip()
    if text[:1] in "[{":
        try:
            tiers: List[List[str]] = [[], [], []]
            _walk_json(json.loads(text), tiers)
            for tier in tiers:
                if tier:
                    # Keep order but drop duplicates.
                    return list(dict.fromkeys(tier))
        except ValueError:
            pass
    lines = []
    for line in text.splitlines():
        line = line.strip().strip('",')
        if _looks_like_device(line):
            lines.append(line)
    return list(dict.fromkeys(lines))


def parse_apps(text: str) -> List[str]:
    """Allow-listed executable paths out of HidHideCLI output."""
    text = (text or "").strip()
    if text[:1] in "[{":
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if data is not None:
            found: List[str] = []

            def walk(node):
                if isinstance(node, dict):
                    for value in node.values():
                        walk(value)
                elif isinstance(node, list):
                    for item in node:
                        walk(item)
                elif isinstance(node, str) and node.lower().endswith(".exe"):
                    found.append(node)

            walk(data)
            if found:
                return list(dict.fromkeys(found))
    out = []
    for line in text.splitlines():
        line = line.strip().strip('",')
        if line.lower().endswith(".exe"):
            out.append(line)
    return list(dict.fromkeys(out))


def _matches(entry: str, vid: int, pid: int) -> bool:
    upper = entry.upper()
    return ("VID_%04X" % vid) in upper and ("PID_%04X" % pid) in upper


def status() -> Status:
    """What HidHide currently holds, as far as the CLI will tell us."""
    st = Status(elevated=is_elevated(), driver_present=driver_present())
    cli = find_cli()
    if not cli:
        return st
    st.installed = True
    st.cli_path = cli
    try:
        rc, out = run_cli(["--dev-list"], cli)
        if rc == 0:
            st.hidden = parse_devices(out)
        rc, out = run_cli(["--app-list"], cli)
        if rc == 0:
            st.allowed = parse_apps(out)
        rc, out = run_cli(["--cloak-state"], cli)
        if rc == 0:
            st.cloaking = "on" in out.lower() and "off" not in out.lower()
        else:
            # Older builds have no --cloak-state; infer from there being
            # anything to hide at all.
            st.cloaking = bool(st.hidden)
    except HidHideError as exc:
        st.error = str(exc)
    return st


def known_devices() -> List[str]:
    """Every device instance path HidHide can see."""
    rc, out = run_cli(["--dev-all"])
    if rc != 0:
        raise HidHideError("HidHideCLI --dev-all failed: %s" % out.strip())
    return parse_devices(out)


def device_paths_for(vid: int, pid: int) -> List[str]:
    """The instance paths of every collection of one USB device."""
    return [entry for entry in known_devices() if _matches(entry, vid, pid)]


def plan_install(device_paths: List[str], exe: str) -> List[Step]:
    """Commands that hide the tablet and let this program through."""
    steps = [
        Step(["--app-reg", exe], "let this program read the tablet"),
        Step(["--inv-off"], "treat the app list as an allow list", optional=True),
    ]
    for path in device_paths:
        steps.append(Step(["--dev-hide", path], "hide %s from Windows" % _short(path)))
    steps.append(Step(["--cloak-on"], "switch hiding on"))
    return steps


def plan_remove(device_paths: List[str], exe: str) -> List[Step]:
    """Commands that put everything back the way it was."""
    steps = [
        Step(["--dev-unhide", path], "show %s to Windows again" % _short(path))
        for path in device_paths
    ]
    steps.append(Step(["--app-unreg", exe], "drop this program from the allow list"))
    return steps


def _short(path: str) -> str:
    tail = path.rsplit("\\", 1)[-1]
    return tail[:40] if tail else path[:40]


def apply(steps: List[Step], dry_run: bool = False, log=None) -> bool:
    """Run a plan. Returns True when every required step succeeded."""
    say = log or (lambda msg: None)
    if not dry_run and not is_elevated():
        raise HidHideError(
            "changing the HidHide configuration needs administrator rights. "
            "Restart this program as administrator."
        )
    ok = True
    for step in steps:
        if dry_run:
            say("would run: HidHideCLI %s   (%s)" % (step, step.why))
            continue
        rc, out = run_cli(step.args)
        if rc == 0:
            say("ok: %s" % step.why)
        elif step.optional:
            say("skipped (not supported by this HidHide build): %s" % step)
        else:
            ok = False
            say("FAILED: HidHideCLI %s -> %s" % (step, out.strip() or "rc=%d" % rc))
    return ok


def relaunch_as_admin(extra_args: Optional[List[str]] = None) -> bool:
    """Ask Windows to start this program again, elevated."""
    if sys.platform != "win32":
        return False
    args = list(sys.argv[1:]) + list(extra_args or [])
    if getattr(sys, "frozen", False):
        target, params = sys.executable, args
    else:
        target, params = sys.executable, ["-m", "tabletmidi"] + args
    quoted = " ".join('"%s"' % a for a in params)
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", target, quoted, None, 1)
        return int(rc) > 32
    except Exception:
        return False
