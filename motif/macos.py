"""macOS input-monitoring helpers.

On macOS 15+ / 26, HIToolbox TIS APIs (used by pynput's keyboard listener)
must run on the main thread. Calling them from a CGEventTap thread kills the
process with an uncatchable SIGILL / SIGTRAP.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator

from motif.models import (
    direction_from_delta,
    replay_arrow_for_swipe,
    resolve_space_swipe_direction,
)

_PATCHED = False
_LAYOUT_CACHE: tuple | None = None
_ORIGINAL_CONTEXT = None


class RecorderStartError(RuntimeError):
    """Listener threads failed to start (usually missing macOS permissions)."""


def prepare_input_hooks() -> None:
    """Warm the keyboard layout on this thread, then block off-main TIS calls."""
    if sys.platform != "darwin":
        return
    _install_tis_guard()
    _warm_layout()


def can_monitor_input() -> bool:
    """True when Accessibility (and Input Monitoring, if the OS exposes it) allow taps."""
    if sys.platform != "darwin":
        return True
    trusted = _ax_trusted()
    listen = _listen_event_access()
    if listen is None:
        return trusted
    return trusted or listen


def listener_start_help() -> str:
    """Why input listeners failed, in platform-honest language."""
    if sys.platform == "darwin":
        return (
            "Could not start the input listeners.\n\n"
            "Grant Accessibility and Input Monitoring to Motif, then quit "
            "and open Motif.app again."
        )
    if sys.platform.startswith("linux"):
        return (
            "Could not start the input listeners.\n\n"
            "On X11, Motif can record globally. On Wayland, global hooks are "
            "restricted — use an X11 session. You may also need to be in the "
            "input group."
        )
    return (
        "Could not start the input listeners.\n\n"
        "Allow Motif through Windows security prompts, then try again."
    )


def is_motif_app() -> bool:
    """True when this process is Motif.app (TCC should list Motif)."""
    import os
    from pathlib import Path

    if os.environ.get("MOTIF_BUNDLE") == "1":
        return True
    candidates = [os.environ.get("PYTHONEXECUTABLE", ""), sys.argv[0] if sys.argv else ""]
    try:
        candidates.append(sys.executable)
    except Exception:
        pass
    for raw in candidates:
        if not raw:
            continue
        try:
            path = str(Path(raw).resolve())
        except OSError:
            path = raw
        if path.endswith("/Motif.app/Contents/MacOS/Motif"):
            return True
    return False


def permissions_help() -> str:
    if sys.platform == "darwin":
        return (
            "Grant these to the Motif you opened — project Motif.app or "
            "/Applications/Motif.app — not Terminal, Motif.command, or Python:\n\n"
            "1. System Settings → Privacy & Security → Accessibility\n"
            "2. System Settings → Privacy & Security → Input Monitoring\n"
            "3. System Settings → Privacy & Security → Screen Recording  "
            "(only needed for colour triggers)\n\n"
            "Local Network is not required. Open that Motif, tick it in each list, "
            "then quit and open the same Motif.app again."
        )
    if sys.platform.startswith("linux"):
        return (
            "On X11, Motif can record globally.\n"
            "On Wayland, global hooks are restricted — use an X11 session for "
            "full record/replay.\n"
            "uinput / input group access may also be required."
        )
    return (
        "On Windows, allow Motif through security prompts. High-DPI scaling "
        "is handled automatically."
    )


def prompt_os_permission_dialogs() -> None:
    """Ask macOS to attach Accessibility / Input Monitoring to this process.

    Only when running as Motif.app — prompting from Terminal would list Terminal.
    """
    if sys.platform != "darwin" or not is_motif_app():
        return
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    except Exception:
        pass
    try:
        from Quartz import CGPreflightListenEventAccess, CGRequestListenEventAccess

        if not CGPreflightListenEventAccess():
            CGRequestListenEventAccess()
    except Exception:
        pass
    try:
        from Quartz import CGPreflightPostEventAccess, CGRequestPostEventAccess

        if not CGPreflightPostEventAccess():
            CGRequestPostEventAccess()
    except Exception:
        pass


def _ax_trusted() -> bool:
    try:
        from HIServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _listen_event_access() -> bool | None:
    try:
        from Quartz import CGPreflightListenEventAccess

        return bool(CGPreflightListenEventAccess())
    except Exception:
        return None


def _warm_layout() -> None:
    global _LAYOUT_CACHE
    if _ORIGINAL_CONTEXT is None:
        return
    with _ORIGINAL_CONTEXT() as context:
        _LAYOUT_CACHE = context


def _install_tis_guard() -> None:
    global _PATCHED, _ORIGINAL_CONTEXT
    if _PATCHED or sys.platform != "darwin":
        return
    from pynput._util import darwin as pynput_darwin

    _ORIGINAL_CONTEXT = pynput_darwin.keycode_context

    @contextlib.contextmanager
    def guarded() -> Iterator:
        if threading.current_thread() is threading.main_thread():
            with _ORIGINAL_CONTEXT() as context:
                global _LAYOUT_CACHE
                _LAYOUT_CACHE = context
                yield context
            return
        cached = _LAYOUT_CACHE
        if cached is None:
            # Never call TIS off-main: that is SIGILL on recent macOS.
            yield (None, None)
            return
        yield cached

    pynput_darwin.keycode_context = guarded
    try:
        from pynput.keyboard import _darwin as keyboard_darwin

        keyboard_darwin.keycode_context = guarded
    except Exception:
        pass
    _PATCHED = True


# Four-finger Mission Control / space swipes are usually eaten by the Window
# Server. Gestures only hint direction. Each NSWorkspace space change becomes
# its own swipe event so leaving and returning are both recorded.

_GESTURE_TYPES = {19, 20, 29, 30, 31}  # begin, end, gesture, magnify, swipe
_SWIPE_DEDUPE_S = 0.18
_SWITCH_DEDUPE_S = 0.40
_APP_SETTLE_S = 0.22
_HINT_TTL_S = 0.85
_STOP_SPACE_WAIT_S = 0.80
_ARROW_KEYCODES = {"left": 123, "right": 124, "down": 125, "up": 126}
_CONTROL_KEYCODE = 59
_KEY_EVENT_GAP_S = 0.012
_SPACE_WATCH_S = 0.28
MOTIF_BUNDLE_ID = "app.motif.recorder"

SWIPE_INFERRED_NOTE = (
    "Space change without an app identity — macOS does not deliver "
    "four-finger Mission Control swipes to apps. Consecutive changes are a "
    "horizontal pair (right = Move right a space, then the opposite return). "
    "The stored ctrl+left / ctrl+right shortcut is what Replay posts. Flip "
    "Direction if Replay goes the wrong way."
)
SWIPE_SHORTCUT_NOTE = (
    "Replay posts the stored Control+Arrow shortcut, not a trackpad swipe. "
    "Fullscreen apps use Move left/right a space — Control+Up is Mission Control."
)
SWITCH_APP_NOTE = (
    "Replay brings this app forward — not a four-finger swipe. "
    "If activate fails, Motif posts the stored Control+Arrow space shortcut."
)


def post_space_switch(
    direction: str,
    keyboard,
    *,
    native: bool | None = None,
    key: str = "",
    inferred: bool = False,
) -> str:
    """Replay a space/fullscreen swipe. Returns 'gesture' or 'shortcut'."""
    arrow = replay_arrow_for_swipe(direction, inferred=inferred, key=key)
    if native is None:
        native = sys.platform == "darwin" and not os.environ.get("PYTEST_CURRENT_TEST")
    if native and _post_gesture_swipe(arrow):
        return "gesture"
    before = _space_fingerprint() if native else ()
    if native and _post_control_arrow_event(arrow):
        if _space_changed(before, _SPACE_WATCH_S) or not before:
            return "shortcut"
    if native and _post_system_events_arrow(arrow):
        return "shortcut"
    from motif.keys import name_to_key

    key_obj = name_to_key(arrow)
    ctrl = name_to_key("ctrl")
    if key_obj is None or ctrl is None:
        return "shortcut"
    keyboard.press(ctrl)
    keyboard.press(key_obj)
    keyboard.release(key_obj)
    keyboard.release(ctrl)
    return "shortcut"


def frontmost_app_info() -> tuple[str, str]:
    """Localized name and bundle id of the frontmost app, if available."""
    if sys.platform != "darwin":
        return "", ""
    try:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return "", ""
        name = str(app.localizedName() or "")
        bundle = str(app.bundleIdentifier() or "")
        return name, bundle
    except Exception:
        return "", ""


def frontmost_app_name() -> str:
    """Localized name of the frontmost app after a space change, if available."""
    name, bundle = frontmost_app_info()
    return name or bundle


def current_app_identity() -> tuple[str, str]:
    """This process — used so Motif becoming key is not recorded as a switch."""
    if sys.platform != "darwin":
        return "", ""
    try:
        from AppKit import NSRunningApplication

        app = NSRunningApplication.currentApplication()
        if app is None:
            return "", ""
        return str(app.localizedName() or ""), str(app.bundleIdentifier() or "")
    except Exception:
        return "", ""


def is_motif_application(name: str = "", bundle_id: str = "") -> bool:
    """True when this identity is Motif itself (or the recording process)."""
    bundle = (bundle_id or "").strip().lower()
    label = (name or "").strip().lower()
    if bundle == MOTIF_BUNDLE_ID or label == "motif":
        return True
    ours_name, ours_bundle = current_app_identity()
    if ours_bundle and bundle and bundle == ours_bundle.strip().lower():
        return True
    if ours_name and label and label == ours_name.strip().lower() and label in {"motif"}:
        return True
    return False


def app_from_notification(notification) -> tuple[str, str]:
    if sys.platform != "darwin":
        return "", ""
    try:
        from AppKit import NSWorkspaceApplicationKey

        info = notification.userInfo() if notification is not None else None
        app = None
        if info is not None:
            try:
                app = info.objectForKey_(NSWorkspaceApplicationKey)
            except Exception:
                app = info.get(NSWorkspaceApplicationKey) if hasattr(info, "get") else None
        if app is None:
            return "", ""
        return str(app.localizedName() or ""), str(app.bundleIdentifier() or "")
    except Exception:
        return "", ""


def activate_app(bundle_id: str = "", name: str = "") -> bool:
    """Bring a recorded app forward. Not a four-finger gesture."""
    if sys.platform != "darwin":
        return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    bundle_id = (bundle_id or "").strip()
    name = (name or "").strip()
    if not bundle_id and not name:
        return False
    try:
        from AppKit import NSRunningApplication, NSWorkspace
    except Exception:
        return False
    try:
        from AppKit import NSApplicationActivateIgnoringOtherApps

        options = int(NSApplicationActivateIgnoringOtherApps)
    except Exception:
        options = 1
    try:
        if bundle_id:
            running = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
            for app in running or []:
                try:
                    if app.activateWithOptions_(options):
                        return True
                except Exception:
                    continue
            ws = NSWorkspace.sharedWorkspace()
            ok = ws.launchAppWithBundleIdentifier_options_additionalEventParamDescriptor_launchIdentifier_(
                bundle_id,
                0,
                None,
                None,
            )
            if ok:
                return True
        if name:
            ws = NSWorkspace.sharedWorkspace()
            for app in ws.runningApplications() or []:
                try:
                    label = str(app.localizedName() or "")
                except Exception:
                    continue
                if label.lower() == name.lower() and app.activateWithOptions_(options):
                    return True
    except Exception:
        return False
    return False


def _post_gesture_swipe(_direction: str) -> bool:
    """Native four-finger swipes cannot be posted to Mission Control; use the shortcut."""
    return False


def _arrow_event_flags():
    """Arrow keys need the Fn (and often numeric-pad) bit or macOS ignores them."""
    if sys.platform != "darwin":
        return 0
    from Quartz import kCGEventFlagMaskControl, kCGEventFlagMaskSecondaryFn

    flags = kCGEventFlagMaskControl | kCGEventFlagMaskSecondaryFn
    try:
        from Quartz import kCGEventFlagMaskNumericPad

        flags |= kCGEventFlagMaskNumericPad
    except Exception:
        pass
    return flags


def _post_control_arrow_event(arrow: str) -> bool:
    """Post Control+Arrow at the HID tap so Qt / Motif focus cannot eat it."""
    if sys.platform != "darwin":
        return False
    keycode = _ARROW_KEYCODES.get(arrow)
    if keycode is None:
        return False
    try:
        from Quartz import (
            CGEventCreateKeyboardEvent,
            CGEventPost,
            CGEventSetFlags,
            kCGHIDEventTap,
        )
    except Exception:
        return False
    try:
        flags = _arrow_event_flags()
        ctrl_down = CGEventCreateKeyboardEvent(None, _CONTROL_KEYCODE, True)
        CGEventSetFlags(ctrl_down, flags)
        CGEventPost(kCGHIDEventTap, ctrl_down)
        time.sleep(_KEY_EVENT_GAP_S)
        arrow_down = CGEventCreateKeyboardEvent(None, keycode, True)
        CGEventSetFlags(arrow_down, flags)
        CGEventPost(kCGHIDEventTap, arrow_down)
        time.sleep(_KEY_EVENT_GAP_S)
        arrow_up = CGEventCreateKeyboardEvent(None, keycode, False)
        CGEventSetFlags(arrow_up, flags)
        CGEventPost(kCGHIDEventTap, arrow_up)
        time.sleep(_KEY_EVENT_GAP_S)
        ctrl_up = CGEventCreateKeyboardEvent(None, _CONTROL_KEYCODE, False)
        CGEventPost(kCGHIDEventTap, ctrl_up)
        return True
    except Exception:
        return False


def _post_system_events_arrow(arrow: str) -> bool:
    """Accessibility fallback: System Events types Control+Arrow."""
    if sys.platform != "darwin":
        return False
    keycode = _ARROW_KEYCODES.get(arrow)
    if keycode is None:
        return False
    try:
        import subprocess

        script = f"tell application \"System Events\" to key code {keycode} using control down"
        completed = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            timeout=4,
            capture_output=True,
        )
        return completed.returncode == 0
    except Exception:
        return False


def _space_fingerprint() -> tuple:
    """On-screen window ids — changes when the active space / fullscreen app does."""
    if sys.platform != "darwin":
        return ()
    try:
        from Quartz import CGWindowListCopyWindowInfo, kCGNullWindowID, kCGWindowListOptionOnScreenOnly

        windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
    except Exception:
        return ()
    found: list[tuple[int, str]] = []
    for window in windows or []:
        try:
            number = window.get("kCGWindowNumber") or window.get("WindowNumber") or 0
            owner = window.get("kCGWindowOwnerName") or window.get("OwnerName") or ""
            found.append((int(number or 0), str(owner)))
        except Exception:
            continue
    return tuple(found[:48])


def _space_changed(before: tuple, timeout_s: float) -> bool:
    if not before:
        return False
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        now = _space_fingerprint()
        if now and now != before:
            return True
        time.sleep(0.03)
    return False


class SwipeCapture:
    """Record desktop/fullscreen/app switches on macOS.

    Gestures only hint a Control+Arrow fallback. A row is emitted when the
    desktop or frontmost app actually changes — never from an `up` gesture
    alone. Space change + app activate for the same switch is one event.
    """

    def __init__(self, on_swipe: Callable[..., None]) -> None:
        self.on_swipe = on_swipe
        self._lock = threading.Lock()
        self._hint = ""
        self._hint_at = 0.0
        self._hint_used = False
        self._gesture_at = 0.0
        self._last_direction = ""
        self._last_app = ""
        self._last_bundle = ""
        self._emitted_at = 0.0
        self._pending_space = False
        self._pending_way = ""
        self._pending_inferred = False
        self._pending_timer: threading.Timer | None = None
        self._monitors: list = []
        self._observer = None
        self._center = None
        self._tap = None
        self._tap_source = None
        self._tap_thread: threading.Thread | None = None
        self._loop = None
        self._running = False

    def hint(self, direction: str) -> None:
        # Any gesture marks a possible pending space-change so stop() can wait
        # for NSWorkspace. Only left/right become the stored direction hint.
        with self._lock:
            self._gesture_at = time.monotonic()
        if direction not in {"left", "right"}:
            return
        with self._lock:
            self._hint = direction
            self._hint_at = time.monotonic()
            self._hint_used = False

    def hint_from_delta(self, dx: float, dy: float) -> None:
        way = direction_from_delta(dx, dy)
        if way in {"left", "right"}:
            self.hint(way)

    def start(self) -> None:
        if sys.platform != "darwin" or self._running:
            return
        self._running = True
        self._start_ns_monitors()
        self._start_space_observer()
        self._start_gesture_tap()

    def flush_pending(self, pump: Callable[[], None] | None = None) -> None:
        """Emit a swipe for a space change that has not been recorded yet.

        Four-finger swipes often arrive as an 'up' gesture; the real signal is
        NSWorkspaceActiveSpaceDidChange, which can lag ~0.6s. Stop must pump
        the main loop so that notification is delivered before we tear down.
        An unused left/right hint is emitted immediately.
        """
        if self._unused_hint():
            self._force_space_change()
            self._flush_pending_space()
            return
        if not self._recent_unconsumed_gesture():
            self._flush_pending_space()
            return
        deadline = time.monotonic() + _STOP_SPACE_WAIT_S
        while time.monotonic() < deadline and self._running:
            if pump is not None:
                try:
                    pump()
                except Exception:
                    pass
            if self._emitted_since_gesture():
                self._flush_pending_space()
                return
            time.sleep(0.02)
        if self._unused_hint():
            self._force_space_change()
        self._flush_pending_space()

    def _force_space_change(self) -> None:
        running = self._running
        self._running = True
        try:
            self.handle_space_change()
        finally:
            self._running = running

    def _unused_hint(self) -> bool:
        with self._lock:
            if self._hint_used or not self._hint:
                return False
            return time.monotonic() - self._hint_at < _HINT_TTL_S

    def _recent_unconsumed_gesture(self) -> bool:
        with self._lock:
            if self._gesture_at <= 0:
                return False
            if self._emitted_at and self._emitted_at >= self._gesture_at:
                return False
            return time.monotonic() - self._gesture_at < _HINT_TTL_S

    def _emitted_since_gesture(self) -> bool:
        with self._lock:
            return bool(self._emitted_at and self._emitted_at >= self._gesture_at)

    def stop(self) -> None:
        self._running = False
        self._cancel_pending_timer()
        with self._lock:
            self._pending_space = False
        if sys.platform == "darwin":
            for mon in self._monitors:
                try:
                    from AppKit import NSEvent

                    NSEvent.removeMonitor_(mon)
                except Exception:
                    pass
            if self._observer is not None and self._center is not None:
                try:
                    self._center.removeObserver_(self._observer)
                except Exception:
                    pass
            loop = self._loop
            if loop is not None:
                try:
                    from Quartz import CFRunLoopStop

                    CFRunLoopStop(loop)
                except Exception:
                    pass
        self._monitors.clear()
        self._observer = None
        self._center = None
        if self._tap_thread and self._tap_thread.is_alive():
            self._tap_thread.join(timeout=1.0)
        self._tap_thread = None
        self._tap = None
        self._tap_source = None
        self._loop = None

    def handle_space_change(self) -> None:
        """Record one switch for this space/fullscreen change (leave or return)."""
        if self._has_pending_space():
            self._flush_pending_space()
        hint = self._take_hint()
        with self._lock:
            last = self._last_direction
        way, inferred = resolve_space_swipe_direction(hint, last)
        # Always wait a beat for didActivateApplication so we store the app
        # that became frontmost, not the one that just lost the space.
        self._hold_pending_space(way, inferred)

    def handle_app_activate(
        self,
        name: str = "",
        bundle_id: str = "",
        notification=None,
    ) -> None:
        """Frontmost app changed. Coalesce with a pending space change."""
        if not self._running:
            return
        if notification is not None:
            note_name, note_bundle = app_from_notification(notification)
            name = name or note_name
            bundle_id = bundle_id or note_bundle
        if not name and not bundle_id:
            name, bundle_id = frontmost_app_info()
        if is_motif_application(name, bundle_id):
            return
        if not name and not bundle_id:
            return
        with self._lock:
            pending = self._pending_space
            pending_way = self._pending_way
            pending_inferred = self._pending_inferred
            emitted_at = self._emitted_at
        now = time.monotonic()
        if pending:
            self._emit(pending_way, pending_inferred, name, bundle_id)
            return
        if emitted_at and now - emitted_at < _SWITCH_DEDUPE_S:
            return
        self._emit("", False, name, bundle_id)

    def _has_pending_space(self) -> bool:
        with self._lock:
            return self._pending_space

    def _hold_pending_space(self, way: str, inferred: bool) -> None:
        with self._lock:
            self._pending_space = True
            self._pending_way = way
            self._pending_inferred = inferred
        self._arm_pending_timer()

    def _arm_pending_timer(self) -> None:
        self._cancel_pending_timer()
        timer = threading.Timer(_APP_SETTLE_S, self._flush_pending_space)
        timer.daemon = True
        self._pending_timer = timer
        timer.start()

    def _cancel_pending_timer(self) -> None:
        timer = self._pending_timer
        self._pending_timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass

    def _flush_pending_space(self) -> None:
        with self._lock:
            if not self._pending_space:
                return
            way = self._pending_way
            inferred = self._pending_inferred
            self._pending_space = False
        self._cancel_pending_timer()
        name, bundle = _usable_frontmost()
        self._emit(way, inferred, name, bundle)

    def _emit(self, direction: str, inferred: bool, app: str = "", bundle_id: str = "") -> None:
        way = direction or ""
        with self._lock:
            now = time.monotonic()
            if way and way == self._last_direction and now - self._emitted_at < _SWIPE_DEDUPE_S:
                self._hint_used = True
                self._pending_space = False
                return
            if not way and (app or bundle_id) and now - self._emitted_at < _SWITCH_DEDUPE_S:
                self._hint_used = True
                self._pending_space = False
                return
            if way:
                self._last_direction = way
            self._last_app = app
            self._last_bundle = bundle_id
            self._emitted_at = now
            self._hint_used = True
            self._pending_space = False
        self._cancel_pending_timer()
        if self._running:
            self._notify(way, inferred, app, bundle_id)

    def _notify(self, direction: str, inferred: bool, app: str = "", bundle_id: str = "") -> None:
        try:
            self.on_swipe(direction, inferred, app, bundle_id)
        except TypeError:
            self.on_swipe(direction or "right", inferred)

    def _take_hint(self) -> str:
        with self._lock:
            if self._hint_used or not self._hint:
                return ""
            if time.monotonic() - self._hint_at >= _HINT_TTL_S:
                return ""
            return self._hint

    def _fresh_hint(self) -> str:
        return self._take_hint()

    def _start_ns_monitors(self) -> None:
        if sys.platform != "darwin":
            return
        try:
            from AppKit import (
                NSEvent,
                NSEventMaskBeginGesture,
                NSEventMaskEndGesture,
                NSEventMaskGesture,
                NSEventMaskSwipe,
            )
        except Exception:
            return

        def note(event) -> None:
            if not self._running:
                return
            way = _ns_swipe_direction(event)
            if way:
                self.hint(way)

        def keep(event):
            note(event)
            return event

        mask = 0
        for name in (NSEventMaskSwipe, NSEventMaskGesture, NSEventMaskBeginGesture, NSEventMaskEndGesture):
            try:
                mask |= int(name)
            except Exception:
                pass
        if not mask:
            return
        try:
            mon = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(mask, note)
            if mon is not None:
                self._monitors.append(mon)
        except Exception:
            pass
        try:
            mon = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(mask, keep)
            if mon is not None:
                self._monitors.append(mon)
        except Exception:
            pass

    def _start_space_observer(self) -> None:
        if sys.platform != "darwin":
            return
        try:
            from AppKit import (
                NSWorkspace,
                NSWorkspaceActiveSpaceDidChangeNotification,
                NSWorkspaceDidActivateApplicationNotification,
            )
            from Foundation import NSObject
        except Exception:
            return

        capture = self

        class _Observer(NSObject):
            def spaceChanged_(self, _notification) -> None:  # noqa: N802
                if not capture._running:
                    return
                capture.handle_space_change()

            def appActivated_(self, notification) -> None:  # noqa: N802
                if not capture._running:
                    return
                capture.handle_app_activate(notification=notification)

        try:
            observer = _Observer.alloc().init()
            center = NSWorkspace.sharedWorkspace().notificationCenter()
            center.addObserver_selector_name_object_(
                observer,
                "spaceChanged:",
                NSWorkspaceActiveSpaceDidChangeNotification,
                None,
            )
            center.addObserver_selector_name_object_(
                observer,
                "appActivated:",
                NSWorkspaceDidActivateApplicationNotification,
                None,
            )
            self._observer = observer
            self._center = center
        except Exception:
            self._observer = None
            self._center = None

    def _start_gesture_tap(self) -> None:
        if sys.platform != "darwin":
            return
        try:
            from Quartz import (
                CFMachPortCreateRunLoopSource,
                CFRunLoopAddSource,
                CFRunLoopGetCurrent,
                CFRunLoopRun,
                CGEventGetDoubleValueField,
                CGEventTapCreate,
                CGEventTapEnable,
                kCFRunLoopCommonModes,
                kCGEventTapOptionListenOnly,
                kCGHeadInsertEventTap,
                kCGHIDEventTap,
            )
        except Exception:
            return

        mask = 0
        for bit in _GESTURE_TYPES:
            mask |= 1 << bit

        capture = self

        def callback(_proxy, event_type, event, _refcon):
            if not capture._running:
                return event
            try:
                kind = int(event_type)
            except Exception:
                return event
            if kind not in _GESTURE_TYPES:
                return event
            dx = dy = 0.0
            for field in (60, 61, 92, 93, 115, 116):
                try:
                    value = float(CGEventGetDoubleValueField(event, field))
                except Exception:
                    continue
                if abs(value) > abs(dx) and abs(value) >= abs(dy) and abs(value) > 0.05:
                    if field % 2 == 0:
                        dx = value
                    else:
                        dy = value
            way = direction_from_delta(dx, dy)
            if way:
                capture.hint(way)
            return event

        def run() -> None:
            try:
                tap = CGEventTapCreate(
                    kCGHIDEventTap,
                    kCGHeadInsertEventTap,
                    kCGEventTapOptionListenOnly,
                    mask,
                    callback,
                    None,
                )
            except Exception:
                tap = None
            if tap is None:
                try:
                    from Quartz import kCGSessionEventTap

                    tap = CGEventTapCreate(
                        kCGSessionEventTap,
                        kCGHeadInsertEventTap,
                        kCGEventTapOptionListenOnly,
                        mask,
                        callback,
                        None,
                    )
                except Exception:
                    return
            if tap is None:
                return
            try:
                source = CFMachPortCreateRunLoopSource(None, tap, 0)
                loop = CFRunLoopGetCurrent()
                CFRunLoopAddSource(loop, source, kCFRunLoopCommonModes)
                CGEventTapEnable(tap, True)
                capture._tap = tap
                capture._tap_source = source
                capture._loop = loop
                CFRunLoopRun()
            except Exception:
                return

        self._tap_thread = threading.Thread(target=run, name="motif-swipe-tap", daemon=True)
        self._tap_thread.start()


def _usable_frontmost() -> tuple[str, str]:
    name, bundle = frontmost_app_info()
    if is_motif_application(name, bundle):
        return "", ""
    return name, bundle


def _ns_swipe_direction(event) -> str:
    try:
        dx = float(event.deltaX())
        dy = float(event.deltaY())
        way = direction_from_delta(dx, dy)
        if way:
            return way
    except Exception:
        pass
    try:
        raw = int(event.swipeDirection())
        return {1: "right", 2: "left", 4: "up", 8: "down"}.get(raw, "")
    except Exception:
        return ""
