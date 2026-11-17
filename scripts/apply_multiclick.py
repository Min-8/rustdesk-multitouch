#!/usr/bin/env python3
"""Patch a pinned RustDesk source tree. Fail if source anchors change."""
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

def replace_once(relative, before, after):
    path = root / relative
    data = path.read_text(encoding="utf-8")
    n = data.count(before)
    if n != 1:
        raise RuntimeError(f"{relative}: expected 1 matching anchor, found {n}: {before[:70]}")
    path.write_text(data.replace(before, after, 1), encoding="utf-8", newline="\n")

rust = "src/flutter_ffi.rs"
dart = "flutter/lib/desktop/pages/remote_page.dart"

replace_once(rust,
    "    static ref TEXTURE_RENDER_KEY: Arc<AtomicI32> = Arc::new(AtomicI32::new(0));\n",
    """    static ref TEXTURE_RENDER_KEY: Arc<AtomicI32> = Arc::new(AtomicI32::new(0));
    // Opt-in single broadcaster. In-memory only; OFF after restarting.
    static ref MOUSE_BROADCAST_SOURCE: std::sync::Mutex<Option<SessionID>> =
        std::sync::Mutex::new(None);
""")

replace_once(rust,
    """pub fn main_get_local_option(key: String) -> SyncReturn<String> {
    SyncReturn(get_local_option(key))
}""",
    """pub fn main_get_local_option(key: String) -> SyncReturn<String> {
    if key == "mouse-broadcast-source" {
        let active = MOUSE_BROADCAST_SOURCE.lock().unwrap();
        return SyncReturn(active.as_ref().map(ToString::to_string).unwrap_or_default());
    }
    SyncReturn(get_local_option(key))
}""")

replace_once(rust,
    """pub fn main_set_local_option(key: String, value: String) {
    let is_texture_render_key = key.eq(keys::OPTION_TEXTURE_RENDER);""",
    """pub fn main_set_local_option(key: String, value: String) {
    if key == "mouse-broadcast-source" {
        *MOUSE_BROADCAST_SOURCE.lock().unwrap() = uuid::Uuid::parse_str(&value).ok();
        return;
    }
    let is_texture_render_key = key.eq(keys::OPTION_TEXTURE_RENDER);""")

replace_once(rust,
    """        if let Some(session) = sessions::get_session_by_session_id(&session_id) {
            session.send_mouse(mask, x, y, alt, ctrl, shift, command);
        }
    }
}

pub fn session_restart_remote_device""",
    """        if let Some(session) = sessions::get_session_by_session_id(&session_id) {
            session.send_mouse(mask, x, y, alt, ctrl, shift, command);

            // Only absolute motion + left/right press/release. No wheel/relative/touch.
            let regular_move = !m.contains_key("type")
                && m.contains_key("x") && m.contains_key("y");
            let click = matches!(m.get("type").map(String::as_str), Some("down") | Some("up"))
                && matches!(m.get("buttons").map(String::as_str), Some("left") | Some("right"));
            let armed = MOUSE_BROADCAST_SOURCE.lock().unwrap().as_ref() == Some(&session_id);
            if armed && m.get("relative_mouse_mode").is_none() && (regular_move || click) {
                for target in sessions::get_sessions() {
                    if !target.is_default() || Arc::ptr_eq(&session, &target) {
                        continue;
                    }
                    if !target.connection_round_state.lock().unwrap().is_connected() {
                        continue;
                    }
                    target.send_mouse(mask, x, y, alt, ctrl, shift, command);
                }
            }
        }
    }
}

pub fn session_restart_remote_device""")

replace_once(dart,
    """        TickerProviderStateMixin {
  Timer? _timer;""",
    """        TickerProviderStateMixin {
  static const _mouseBroadcastKey = 'mouse-broadcast-source';
  Timer? _mouseBroadcastTimer;
  bool _mouseBroadcastEnabled = false;
  Timer? _timer;""")

replace_once(dart,
    """    _ffi = FFI(widget.sessionId);
    if (isMacOS) {""",
    """    _ffi = FFI(widget.sessionId);
    if (isWindows) {
      _mouseBroadcastTimer =
          Timer.periodic(const Duration(milliseconds: 600), (_) {
        if (!mounted) return;
        final active = bind.mainGetLocalOption(key: _mouseBroadcastKey) ==
            sessionId.toString();
        if (active != _mouseBroadcastEnabled) {
          setState(() => _mouseBroadcastEnabled = active);
        }
      });
    }
    if (isMacOS) {""")

replace_once(dart,
    """  Future<void> dispose() async {
    final closeSession = closeSessionOnDispose.remove(widget.id) ?? true;

    // https://github.com/flutter/flutter/issues/64935""",
    """  Future<void> dispose() async {
    final closeSession = closeSessionOnDispose.remove(widget.id) ?? true;
    _mouseBroadcastTimer?.cancel();
    if (isWindows &&
        closeSession &&
        bind.mainGetLocalOption(key: _mouseBroadcastKey) ==
            sessionId.toString()) {
      bind.mainSetLocalOption(key: _mouseBroadcastKey, value: '');
    }

    // https://github.com/flutter/flutter/issues/64935""")

replace_once(dart,
    """              _ffi.ffiModel.pi.isSet.isFalse ? emptyOverlay() : Offstage(),
            ],
          ),""",
    """              _ffi.ffiModel.pi.isSet.isFalse ? emptyOverlay() : Offstage(),
              if (isWindows && !_ffi.inputModel.relativeMouseMode.value)
                Positioned(
                  bottom: 12,
                  right: 12,
                  child: Tooltip(
                    message: 'Repeat clicks on other connected RustDesk remote sessions',
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                        backgroundColor: _mouseBroadcastEnabled
                            ? Colors.deepOrange : Colors.black87,
                        foregroundColor: Colors.white,
                        visualDensity: VisualDensity.compact,
                      ),
                      icon: const Icon(Icons.mouse, size: 18),
                      label: Text(_mouseBroadcastEnabled
                          ? '멀티클릭 ON' : '멀티클릭 OFF'),
                      onPressed: () {
                        final active = bind.mainGetLocalOption(
                            key: _mouseBroadcastKey);
                        final next = active == sessionId.toString()
                            ? '' : sessionId.toString();
                        bind.mainSetLocalOption(
                            key: _mouseBroadcastKey, value: next);
                        if (mounted) {
                          setState(() => _mouseBroadcastEnabled =
                              next == sessionId.toString());
                        }
                      },
                    ),
                  ),
                ),
            ],
          ),""")

print("Patched src/flutter_ffi.rs and flutter/lib/desktop/pages/remote_page.dart")
