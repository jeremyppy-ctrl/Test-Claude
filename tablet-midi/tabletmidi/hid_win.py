"""Raw HID input on Windows, through ctypes.

Windows already parsed the tablet's report descriptor for us, so rather than
decoding raw bytes by hand -- which differs from tablet to tablet -- we ask
HID.DLL where the usages live and let ``HidP_GetUsageValue`` pull them out of
each report. That is what makes this work on an unknown tablet.

The structures are declared with explicit-width fields so that their layout
matches Windows on any host, which lets the test suite check their sizes
without a Windows machine.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import POINTER, Structure, Union, byref, c_void_p, sizeof
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .mapping import PenSample

# Win32 types, pinned to their real widths.
BOOLEAN = ctypes.c_ubyte
UCHAR = ctypes.c_ubyte
USHORT = ctypes.c_ushort
USAGE = ctypes.c_ushort
ULONG = ctypes.c_uint32
LONG = ctypes.c_int32
DWORD = ctypes.c_uint32
HANDLE = c_void_p
ULONG_PTR = ctypes.c_size_t
NTSTATUS = ctypes.c_int32

# Usage pages and usages we care about.
PAGE_GENERIC = 0x01
USAGE_X = 0x30
USAGE_Y = 0x31
PAGE_DIGITIZER = 0x0D
USAGE_TIP_SWITCH = 0x42
USAGE_IN_RANGE = 0x32
USAGE_TIP_PRESSURE = 0x30
USAGE_BARREL_SWITCH = 0x44
USAGE_ERASER = 0x45
USAGE_INVERT = 0x3C

HIDP_INPUT = 0
HIDP_STATUS_SUCCESS = 0x00110000
HIDP_STATUS_USAGE_NOT_FOUND = -0x3FEEFFFC        # 0xC0110004
HIDP_STATUS_INCOMPATIBLE_REPORT_ID = -0x3FEEFFF6  # 0xC011000A

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = c_void_p(-1).value

DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10

ERROR_IO_PENDING = 997
ERROR_ACCESS_DENIED = 5
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102


class GUID(Structure):
    _fields_ = [
        ("Data1", ULONG),
        ("Data2", USHORT),
        ("Data3", USHORT),
        ("Data4", UCHAR * 8),
    ]


class HIDD_ATTRIBUTES(Structure):
    _fields_ = [
        ("Size", ULONG),
        ("VendorID", USHORT),
        ("ProductID", USHORT),
        ("VersionNumber", USHORT),
    ]


class HIDP_CAPS(Structure):
    _fields_ = [
        ("Usage", USAGE),
        ("UsagePage", USAGE),
        ("InputReportByteLength", USHORT),
        ("OutputReportByteLength", USHORT),
        ("FeatureReportByteLength", USHORT),
        ("Reserved", USHORT * 17),
        ("NumberLinkCollectionNodes", USHORT),
        ("NumberInputButtonCaps", USHORT),
        ("NumberInputValueCaps", USHORT),
        ("NumberInputDataIndices", USHORT),
        ("NumberOutputButtonCaps", USHORT),
        ("NumberOutputValueCaps", USHORT),
        ("NumberOutputDataIndices", USHORT),
        ("NumberFeatureButtonCaps", USHORT),
        ("NumberFeatureValueCaps", USHORT),
        ("NumberFeatureDataIndices", USHORT),
    ]


class _RANGE(Structure):
    _fields_ = [
        ("UsageMin", USAGE),
        ("UsageMax", USAGE),
        ("StringMin", USHORT),
        ("StringMax", USHORT),
        ("DesignatorMin", USHORT),
        ("DesignatorMax", USHORT),
        ("DataIndexMin", USHORT),
        ("DataIndexMax", USHORT),
    ]


class _NOT_RANGE(Structure):
    _fields_ = [
        ("Usage", USAGE),
        ("Reserved1", USAGE),
        ("StringIndex", USHORT),
        ("Reserved2", USHORT),
        ("DesignatorIndex", USHORT),
        ("Reserved3", USHORT),
        ("DataIndex", USHORT),
        ("Reserved4", USHORT),
    ]


class _CAPS_UNION(Union):
    _fields_ = [("Range", _RANGE), ("NotRange", _NOT_RANGE)]


class HIDP_BUTTON_CAPS(Structure):
    _fields_ = [
        ("UsagePage", USAGE),
        ("ReportID", UCHAR),
        ("IsAlias", BOOLEAN),
        ("BitField", USHORT),
        ("LinkCollection", USHORT),
        ("LinkUsage", USAGE),
        ("LinkUsagePage", USAGE),
        ("IsRange", BOOLEAN),
        ("IsStringRange", BOOLEAN),
        ("IsDesignatorRange", BOOLEAN),
        ("IsAbsolute", BOOLEAN),
        ("Reserved", ULONG * 10),
        ("u", _CAPS_UNION),
    ]


class HIDP_VALUE_CAPS(Structure):
    _fields_ = [
        ("UsagePage", USAGE),
        ("ReportID", UCHAR),
        ("IsAlias", BOOLEAN),
        ("BitField", USHORT),
        ("LinkCollection", USHORT),
        ("LinkUsage", USAGE),
        ("LinkUsagePage", USAGE),
        ("IsRange", BOOLEAN),
        ("IsStringRange", BOOLEAN),
        ("IsDesignatorRange", BOOLEAN),
        ("IsAbsolute", BOOLEAN),
        ("HasNull", BOOLEAN),
        ("Reserved", UCHAR),
        ("BitSize", USHORT),
        ("ReportCount", USHORT),
        ("Reserved2", USHORT * 5),
        ("UnitsExp", ULONG),
        ("Units", ULONG),
        ("LogicalMin", LONG),
        ("LogicalMax", LONG),
        ("PhysicalMin", LONG),
        ("PhysicalMax", LONG),
        ("u", _CAPS_UNION),
    ]


class SP_DEVICE_INTERFACE_DATA(Structure):
    _fields_ = [
        ("cbSize", DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", DWORD),
        ("Reserved", ULONG_PTR),
    ]


class SP_DEVINFO_DATA(Structure):
    _fields_ = [
        ("cbSize", DWORD),
        ("ClassGuid", GUID),
        ("DevInst", DWORD),
        ("Reserved", ULONG_PTR),
    ]


class OVERLAPPED(Structure):
    _fields_ = [
        ("Internal", ULONG_PTR),
        ("InternalHigh", ULONG_PTR),
        ("Offset", DWORD),
        ("OffsetHigh", DWORD),
        ("hEvent", HANDLE),
    ]


class HidUnavailable(RuntimeError):
    """Raised when the Windows HID stack cannot be reached."""


_dlls = None


def _load():
    """Bind the DLLs on first use, so this module imports anywhere."""
    global _dlls
    if _dlls is not None:
        return _dlls
    if sys.platform != "win32":
        raise HidUnavailable(
            "raw HID access is implemented for Windows only (running on %s)"
            % sys.platform
        )
    hid = ctypes.WinDLL("hid")
    setupapi = ctypes.WinDLL("setupapi")
    kernel32 = ctypes.WinDLL("kernel32")

    hid.HidD_GetHidGuid.argtypes = [POINTER(GUID)]
    hid.HidD_GetHidGuid.restype = None
    hid.HidD_GetAttributes.argtypes = [HANDLE, POINTER(HIDD_ATTRIBUTES)]
    hid.HidD_GetAttributes.restype = BOOLEAN
    hid.HidD_GetPreparsedData.argtypes = [HANDLE, POINTER(c_void_p)]
    hid.HidD_GetPreparsedData.restype = BOOLEAN
    hid.HidD_FreePreparsedData.argtypes = [c_void_p]
    hid.HidD_FreePreparsedData.restype = BOOLEAN
    for name in ("HidD_GetProductString", "HidD_GetManufacturerString"):
        fn = getattr(hid, name)
        fn.argtypes = [HANDLE, c_void_p, ULONG]
        fn.restype = BOOLEAN
    hid.HidD_GetIndexedString.argtypes = [HANDLE, ULONG, c_void_p, ULONG]
    hid.HidD_GetIndexedString.restype = BOOLEAN
    hid.HidP_GetCaps.argtypes = [c_void_p, POINTER(HIDP_CAPS)]
    hid.HidP_GetCaps.restype = NTSTATUS
    hid.HidP_GetValueCaps.argtypes = [
        ctypes.c_int, POINTER(HIDP_VALUE_CAPS), POINTER(USHORT), c_void_p
    ]
    hid.HidP_GetValueCaps.restype = NTSTATUS
    hid.HidP_GetButtonCaps.argtypes = [
        ctypes.c_int, POINTER(HIDP_BUTTON_CAPS), POINTER(USHORT), c_void_p
    ]
    hid.HidP_GetButtonCaps.restype = NTSTATUS
    hid.HidP_GetUsageValue.argtypes = [
        ctypes.c_int, USAGE, USHORT, USAGE, POINTER(ULONG),
        c_void_p, c_void_p, ULONG,
    ]
    hid.HidP_GetUsageValue.restype = NTSTATUS
    hid.HidP_GetUsages.argtypes = [
        ctypes.c_int, USAGE, USHORT, POINTER(USAGE), POINTER(ULONG),
        c_void_p, c_void_p, ULONG,
    ]
    hid.HidP_GetUsages.restype = NTSTATUS
    hid.HidP_MaxUsageListLength.argtypes = [ctypes.c_int, USAGE, c_void_p]
    hid.HidP_MaxUsageListLength.restype = ULONG

    setupapi.SetupDiGetClassDevsW.argtypes = [
        POINTER(GUID), c_void_p, c_void_p, DWORD
    ]
    setupapi.SetupDiGetClassDevsW.restype = HANDLE
    setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
        HANDLE, c_void_p, POINTER(GUID), DWORD,
        POINTER(SP_DEVICE_INTERFACE_DATA),
    ]
    setupapi.SetupDiEnumDeviceInterfaces.restype = ctypes.c_int
    setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        HANDLE, POINTER(SP_DEVICE_INTERFACE_DATA), c_void_p, DWORD,
        POINTER(DWORD), POINTER(SP_DEVINFO_DATA),
    ]
    setupapi.SetupDiGetDeviceInterfaceDetailW.restype = ctypes.c_int
    setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [
        HANDLE, POINTER(SP_DEVINFO_DATA), c_void_p, DWORD, POINTER(DWORD)
    ]
    setupapi.SetupDiGetDeviceInstanceIdW.restype = ctypes.c_int
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [HANDLE]
    setupapi.SetupDiDestroyDeviceInfoList.restype = ctypes.c_int

    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p, DWORD, DWORD, c_void_p, DWORD, DWORD, HANDLE
    ]
    kernel32.CreateFileW.restype = HANDLE
    kernel32.CreateEventW.argtypes = [c_void_p, ctypes.c_int, ctypes.c_int, c_void_p]
    kernel32.CreateEventW.restype = HANDLE
    kernel32.ReadFile.argtypes = [
        HANDLE, c_void_p, DWORD, POINTER(DWORD), POINTER(OVERLAPPED)
    ]
    kernel32.ReadFile.restype = ctypes.c_int
    kernel32.GetOverlappedResult.argtypes = [
        HANDLE, POINTER(OVERLAPPED), POINTER(DWORD), ctypes.c_int
    ]
    kernel32.GetOverlappedResult.restype = ctypes.c_int
    kernel32.WaitForSingleObject.argtypes = [HANDLE, DWORD]
    kernel32.WaitForSingleObject.restype = DWORD
    kernel32.CancelIo.argtypes = [HANDLE]
    kernel32.CancelIo.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [HANDLE]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.ResetEvent.argtypes = [HANDLE]
    kernel32.ResetEvent.restype = ctypes.c_int

    _dlls = (hid, setupapi, kernel32)
    return _dlls


@dataclass
class AxisInfo:
    """Where one absolute axis lives, and how far it travels."""

    usage_page: int
    usage: int
    logical_min: int
    logical_max: int
    bit_size: int


@dataclass
class DeviceInfo:
    """One HID top-level collection, with enough detail to rank it."""

    path: str
    instance_id: str = ""
    vid: int = 0
    pid: int = 0
    version: int = 0
    manufacturer: str = ""
    product: str = ""
    usage_page: int = 0
    usage: int = 0
    input_report_len: int = 0
    x: Optional[AxisInfo] = None
    y: Optional[AxisInfo] = None
    pressure: Optional[AxisInfo] = None
    buttons: List[Tuple[int, int]] = field(default_factory=list)
    readable: bool = False
    note: str = ""

    @property
    def has_pen(self) -> bool:
        return self.x is not None and self.y is not None

    @property
    def has_tip_switch(self) -> bool:
        return (PAGE_DIGITIZER, USAGE_TIP_SWITCH) in self.buttons

    @property
    def has_in_range(self) -> bool:
        return (PAGE_DIGITIZER, USAGE_IN_RANGE) in self.buttons

    def score(self) -> int:
        """How much this collection looks like the pen we want to read."""
        if not self.has_pen:
            return -1
        score = 10
        if self.has_tip_switch:
            score += 40
        if self.has_in_range:
            score += 10
        if self.usage_page == PAGE_DIGITIZER:
            score += 20
        if self.pressure is not None:
            score += 10
        if self.readable:
            score += 15
        # A tablet reporting a wide range is the real digitizer collection,
        # not the coarse mouse-emulation one.
        if self.x is not None and self.x.logical_max >= 4096:
            score += 10
        return score

    def describe(self) -> str:
        bits = ["%04X:%04X" % (self.vid, self.pid)]
        label = (self.product or self.manufacturer).strip()
        if label:
            bits.append(label)
        bits.append("usage %02X:%02X" % (self.usage_page, self.usage))
        if self.has_pen:
            bits.append(
                "X 0-%d Y 0-%d" % (self.x.logical_max, self.y.logical_max)
            )
        flags = []
        if self.has_tip_switch:
            flags.append("tip")
        if self.has_in_range:
            flags.append("in-range")
        if self.pressure is not None:
            flags.append("pressure")
        if flags:
            bits.append("+".join(flags))
        if not self.readable:
            bits.append("NOT READABLE (%s)" % (self.note or "access denied"))
        return " | ".join(bits)


def _wide_string(handle, fn) -> str:
    buf = ctypes.create_unicode_buffer(256)
    if fn(handle, buf, ULONG(sizeof(buf))):
        return buf.value
    return ""


def _find_axis(value_caps, page: int, usage: int) -> Optional[AxisInfo]:
    for cap in value_caps:
        if cap.UsagePage != page:
            continue
        if cap.IsRange:
            if not (cap.u.Range.UsageMin <= usage <= cap.u.Range.UsageMax):
                continue
        elif cap.u.NotRange.Usage != usage:
            continue
        return AxisInfo(page, usage, cap.LogicalMin, cap.LogicalMax, cap.BitSize)
    return None


def _inspect(handle, info: DeviceInfo) -> None:
    """Fill in the usage layout of an opened collection."""
    hid, _, _ = _load()
    pp = c_void_p()
    if not hid.HidD_GetPreparsedData(handle, byref(pp)):
        info.note = "no preparsed data"
        return
    try:
        caps = HIDP_CAPS()
        if hid.HidP_GetCaps(pp, byref(caps)) != HIDP_STATUS_SUCCESS:
            info.note = "HidP_GetCaps failed"
            return
        info.usage_page = caps.UsagePage
        info.usage = caps.Usage
        info.input_report_len = caps.InputReportByteLength

        if caps.NumberInputValueCaps:
            n = USHORT(caps.NumberInputValueCaps)
            arr = (HIDP_VALUE_CAPS * caps.NumberInputValueCaps)()
            if hid.HidP_GetValueCaps(HIDP_INPUT, arr, byref(n), pp) == HIDP_STATUS_SUCCESS:
                values = list(arr)[: n.value]
                info.x = _find_axis(values, PAGE_GENERIC, USAGE_X)
                info.y = _find_axis(values, PAGE_GENERIC, USAGE_Y)
                info.pressure = _find_axis(values, PAGE_DIGITIZER, USAGE_TIP_PRESSURE)

        if caps.NumberInputButtonCaps:
            n = USHORT(caps.NumberInputButtonCaps)
            arr = (HIDP_BUTTON_CAPS * caps.NumberInputButtonCaps)()
            if hid.HidP_GetButtonCaps(HIDP_INPUT, arr, byref(n), pp) == HIDP_STATUS_SUCCESS:
                for cap in list(arr)[: n.value]:
                    if cap.IsRange:
                        lo, hi = cap.u.Range.UsageMin, cap.u.Range.UsageMax
                        # Ranges on a digitizer are short; expand them so the
                        # tip switch is found by an exact membership test.
                        for usage in range(lo, min(hi, lo + 64) + 1):
                            info.buttons.append((cap.UsagePage, usage))
                    else:
                        info.buttons.append((cap.UsagePage, cap.u.NotRange.Usage))
    finally:
        hid.HidD_FreePreparsedData(pp)


def enumerate_devices(only_pens: bool = False) -> List[DeviceInfo]:
    """Every present HID collection, best pen candidate first."""
    hid, setupapi, kernel32 = _load()

    guid = GUID()
    hid.HidD_GetHidGuid(byref(guid))
    dev_info = setupapi.SetupDiGetClassDevsW(
        byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if dev_info == INVALID_HANDLE_VALUE:
        raise HidUnavailable("SetupDiGetClassDevs failed")

    found: List[DeviceInfo] = []
    try:
        index = 0
        iface = SP_DEVICE_INTERFACE_DATA()
        iface.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA)
        while setupapi.SetupDiEnumDeviceInterfaces(
            dev_info, None, byref(guid), index, byref(iface)
        ):
            index += 1
            needed = DWORD(0)
            devinfo = SP_DEVINFO_DATA()
            devinfo.cbSize = sizeof(SP_DEVINFO_DATA)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, byref(iface), None, 0, byref(needed), None
            )
            if not needed.value:
                continue
            buf = ctypes.create_string_buffer(needed.value)
            # SP_DEVICE_INTERFACE_DETAIL_DATA_W: a DWORD size then the path.
            ctypes.cast(buf, POINTER(DWORD))[0] = 8 if sizeof(c_void_p) == 8 else 6
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, byref(iface), buf, needed.value, byref(needed),
                byref(devinfo),
            ):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + sizeof(DWORD))

            instance_id = ""
            size = DWORD(0)
            setupapi.SetupDiGetDeviceInstanceIdW(
                dev_info, byref(devinfo), None, 0, byref(size)
            )
            if size.value:
                id_buf = ctypes.create_unicode_buffer(size.value)
                if setupapi.SetupDiGetDeviceInstanceIdW(
                    dev_info, byref(devinfo), id_buf, size.value, byref(size)
                ):
                    instance_id = id_buf.value

            info = DeviceInfo(path=path, instance_id=instance_id)

            # Query with no access rights: this always succeeds, even for the
            # mouse and keyboard collections Windows keeps to itself.
            handle = kernel32.CreateFileW(
                path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, 0, None,
            )
            if handle == INVALID_HANDLE_VALUE:
                continue
            try:
                attrs = HIDD_ATTRIBUTES()
                attrs.Size = sizeof(HIDD_ATTRIBUTES)
                if hid.HidD_GetAttributes(handle, byref(attrs)):
                    info.vid = attrs.VendorID
                    info.pid = attrs.ProductID
                    info.version = attrs.VersionNumber
                info.product = _wide_string(handle, hid.HidD_GetProductString)
                info.manufacturer = _wide_string(handle, hid.HidD_GetManufacturerString)
                _inspect(handle, info)
            finally:
                kernel32.CloseHandle(handle)

            # Can we actually read from it? That is the question HidHide
            # changes, so probe it separately.
            rh = kernel32.CreateFileW(
                path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, 0, None,
            )
            if rh != INVALID_HANDLE_VALUE:
                info.readable = True
                kernel32.CloseHandle(rh)
            else:
                err = ctypes.GetLastError()
                info.note = (
                    "access denied -- Windows owns this collection"
                    if err == ERROR_ACCESS_DENIED else "error %d" % err
                )

            if only_pens and not info.has_pen:
                continue
            found.append(info)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(dev_info)

    found.sort(key=lambda d: d.score(), reverse=True)
    return found


def pick_device(
    devices: List[DeviceInfo],
    vid: Optional[int] = None,
    pid: Optional[int] = None,
    path: Optional[str] = None,
    name_hint: str = "",
) -> Optional[DeviceInfo]:
    """The best pen collection matching whatever the config pinned down."""
    if path:
        for dev in devices:
            if dev.path.lower() == path.lower():
                return dev
    candidates = [d for d in devices if d.has_pen]
    if vid is not None:
        candidates = [d for d in candidates if d.vid == vid]
    if pid is not None:
        candidates = [d for d in candidates if d.pid == pid]
    if name_hint:
        needle = name_hint.lower()
        narrowed = [
            d for d in candidates
            if needle in d.product.lower() or needle in d.manufacturer.lower()
        ]
        if narrowed:
            candidates = narrowed
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.score())


class PenReader:
    """An opened pen collection, delivering decoded samples."""

    def __init__(self, info: DeviceInfo) -> None:
        hid, _, kernel32 = _load()
        self.info = info
        self._hid = hid
        self._k32 = kernel32

        handle = kernel32.CreateFileW(
            info.path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None,
        )
        if handle == INVALID_HANDLE_VALUE:
            err = ctypes.GetLastError()
            if err == ERROR_ACCESS_DENIED:
                raise HidUnavailable(
                    "Windows refused read access to this collection. Hide the "
                    "tablet with HidHide and allow this program, then retry."
                )
            raise HidUnavailable("could not open the tablet (error %d)" % err)
        self._handle = handle

        self._pp = c_void_p()
        if not hid.HidD_GetPreparsedData(handle, byref(self._pp)):
            kernel32.CloseHandle(handle)
            raise HidUnavailable("could not read the tablet's report descriptor")

        caps = HIDP_CAPS()
        hid.HidP_GetCaps(self._pp, byref(caps))
        self._report_len = max(caps.InputReportByteLength, 1)
        self._buf = ctypes.create_string_buffer(self._report_len)
        self._read = DWORD(0)
        self._ov = OVERLAPPED()
        self._event = kernel32.CreateEventW(None, 1, 0, None)
        self._ov.hEvent = self._event
        self._pending = False

        max_usages = hid.HidP_MaxUsageListLength(HIDP_INPUT, PAGE_DIGITIZER, self._pp)
        self._usage_list = (USAGE * max(int(max_usages), 1))()
        self._usage_len = ULONG(0)
        self._closed = False

    # -- decoding --------------------------------------------------------

    def _value(self, page: int, usage: int) -> Optional[int]:
        out = ULONG(0)
        status = self._hid.HidP_GetUsageValue(
            HIDP_INPUT, page, 0, usage, byref(out), self._pp,
            self._buf, self._read.value,
        )
        if status != HIDP_STATUS_SUCCESS:
            return None
        return out.value

    def _digitizer_usages(self):
        self._usage_len.value = len(self._usage_list)
        status = self._hid.HidP_GetUsages(
            HIDP_INPUT, PAGE_DIGITIZER, 0, self._usage_list,
            byref(self._usage_len), self._pp, self._buf, self._read.value,
        )
        if status != HIDP_STATUS_SUCCESS:
            return None
        return {self._usage_list[i] for i in range(self._usage_len.value)}

    def decode(self, t: float) -> Optional[PenSample]:
        """Turn the report currently in the buffer into a sample."""
        x = self._value(PAGE_GENERIC, USAGE_X)
        y = self._value(PAGE_GENERIC, USAGE_Y)
        if x is None or y is None:
            # Some other report from the same collection -- tablet keys, say.
            return None
        usages = self._digitizer_usages()
        if usages is None:
            tip, in_range = False, True
        else:
            tip = USAGE_TIP_SWITCH in usages
            in_range = USAGE_IN_RANGE in usages if self.info.has_in_range else True
        pressure = self._value(PAGE_DIGITIZER, USAGE_TIP_PRESSURE)
        if not self.info.has_tip_switch and pressure is not None:
            # No tip switch reported: fall back to pressure crossing zero.
            tip = pressure > 0
        return PenSample(
            x=float(x), y=float(y), tip=tip, in_range=in_range,
            pressure=pressure, t=t,
        )

    # -- reading ---------------------------------------------------------

    def read(self, timeout_ms: int = 20) -> Optional[bytes]:
        """One input report, or None if none arrived before the timeout."""
        if self._closed:
            raise HidUnavailable("reader is closed")
        k32 = self._k32
        if not self._pending:
            k32.ResetEvent(self._event)
            ok = k32.ReadFile(
                self._handle, self._buf, self._report_len,
                byref(self._read), byref(self._ov),
            )
            if ok:
                return bytes(self._buf.raw[: self._read.value])
            err = ctypes.GetLastError()
            if err != ERROR_IO_PENDING:
                raise HidUnavailable("read failed (error %d)" % err)
            self._pending = True

        if k32.WaitForSingleObject(self._event, timeout_ms) != WAIT_OBJECT_0:
            return None
        self._pending = False
        if not k32.GetOverlappedResult(
            self._handle, byref(self._ov), byref(self._read), 0
        ):
            raise HidUnavailable("read failed (error %d)" % ctypes.GetLastError())
        return bytes(self._buf.raw[: self._read.value])

    def sample(self, t: float, timeout_ms: int = 20) -> Optional[PenSample]:
        if self.read(timeout_ms) is None:
            return None
        return self.decode(t)

    @property
    def x_limit(self) -> int:
        return self.info.x.logical_max if self.info.x else 0

    @property
    def y_limit(self) -> int:
        return self.info.y.logical_max if self.info.y else 0

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._pending:
            self._k32.CancelIo(self._handle)
        self._hid.HidD_FreePreparsedData(self._pp)
        self._k32.CloseHandle(self._event)
        self._k32.CloseHandle(self._handle)

    def __enter__(self) -> "PenReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def wake_uclogic(info: DeviceInfo) -> bool:
    """Nudge a UC-Logic tablet out of its compatibility mode.

    Medion tablets are usually UC-Logic hardware, which boots pretending to be
    a plain mouse and only switches to full resolution once a driver has read
    two magic string descriptors. Harmless on tablets that do not care.
    """
    hid, _, kernel32 = _load()
    handle = kernel32.CreateFileW(
        info.path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None,
    )
    if handle == INVALID_HANDLE_VALUE:
        return False
    try:
        buf = ctypes.create_unicode_buffer(256)
        woke = False
        for index in (0x64, 0xC8, 0x7B):
            if hid.HidD_GetIndexedString(handle, ULONG(index), buf, ULONG(sizeof(buf))):
                woke = True
        return woke
    finally:
        kernel32.CloseHandle(handle)
