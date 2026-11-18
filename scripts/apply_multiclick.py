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
flutter_core = "src/flutter.rs"
remote_tab = "flutter/lib/desktop/pages/remote_tab_page.dart"

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
            let regular_move = m.get("type").map_or(true, |t| t.is_empty())
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

replace_once(rust,
    """    collections::HashMap,""",
    """    collections::{HashMap, HashSet},""")

replace_once(rust,
    """    static ref MOUSE_BROADCAST_SOURCE: std::sync::Mutex<Option<SessionID>> =
        std::sync::Mutex::new(None);
""",
    """    static ref MOUSE_BROADCAST_SOURCE: std::sync::Mutex<Option<SessionID>> =
        std::sync::Mutex::new(None);
    // Explicitly selected connected remote IDs; no implicit broadcast-to-all.
    static ref MOUSE_BROADCAST_TARGETS: std::sync::Mutex<HashSet<String>> =
        std::sync::Mutex::new(HashSet::new());
""")

replace_once(rust,
    """    if key == "mouse-broadcast-source" {
        let active = MOUSE_BROADCAST_SOURCE.lock().unwrap();
        return SyncReturn(active.as_ref().map(ToString::to_string).unwrap_or_default());
    }
    SyncReturn(get_local_option(key))""",
    """    if key == "mouse-broadcast-source" {
        let active = MOUSE_BROADCAST_SOURCE.lock().unwrap();
        return SyncReturn(active.as_ref().map(ToString::to_string).unwrap_or_default());
    }
    if key == "mouse-broadcast-targets" {
        let mut selected: Vec<String> = MOUSE_BROADCAST_TARGETS.lock().unwrap()
            .iter().cloned().collect();
        selected.sort();
        return SyncReturn(serde_json::to_string(&selected).unwrap_or_else(|_| "[]".into()));
    }
    if let Some(source_uuid) = key.strip_prefix("mouse-broadcast-peers:") {
        let source = uuid::Uuid::parse_str(source_uuid).ok()
            .and_then(|id| sessions::get_session_by_session_id(&id));
        let mut peers = Vec::new();
        if let Some(source) = source {
            for target in sessions::get_sessions() {
                if !target.is_default() || Arc::ptr_eq(&source, &target) ||
                    !target.connection_round_state.lock().unwrap().is_connected() {
                    continue;
                }
                let peer_id = target.lc.read().unwrap().get_id().to_owned();
                if !peer_id.is_empty() {
                    peers.push(peer_id);
                }
            }
        }
        peers.sort();
        peers.dedup();
        return SyncReturn(serde_json::to_string(&peers).unwrap_or_else(|_| "[]".into()));
    }
    SyncReturn(get_local_option(key))""")

replace_once(rust,
    """    if key == "mouse-broadcast-source" {
        *MOUSE_BROADCAST_SOURCE.lock().unwrap() = uuid::Uuid::parse_str(&value).ok();
        return;
    }
    let is_texture_render_key""",
    """    if key == "mouse-broadcast-source" {
        let next = uuid::Uuid::parse_str(&value).ok();
        let mut source = MOUSE_BROADCAST_SOURCE.lock().unwrap();
        if *source != next {
            // Switching or disabling the source must never keep targets armed.
            MOUSE_BROADCAST_TARGETS.lock().unwrap().clear();
        }
        *source = next;
        return;
    }
    if key == "mouse-broadcast-targets" {
        let requested = match serde_json::from_str::<Vec<String>>(&value) {
            Ok(ids) => ids,
            Err(_) => {
                log::warn!("Ignoring malformed mouse-broadcast target selection");
                return;
            }
        };
        // Only connected default remote-control peers can be selected.
        let connected: HashSet<String> = sessions::get_sessions()
            .into_iter()
            .filter(|s| s.is_default() &&
                s.connection_round_state.lock().unwrap().is_connected())
            .map(|s| s.lc.read().unwrap().get_id().to_owned())
            .collect();
        *MOUSE_BROADCAST_TARGETS.lock().unwrap() = requested
            .into_iter().filter(|id| connected.contains(id)).collect();
        return;
    }
    let is_texture_render_key""")

replace_once(rust,
    """            let armed = MOUSE_BROADCAST_SOURCE.lock().unwrap().as_ref() == Some(&session_id);
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
            }""",
    """            let armed = MOUSE_BROADCAST_SOURCE.lock().unwrap().as_ref() == Some(&session_id);
            if armed && m.get("relative_mouse_mode").is_none() && (regular_move || click) {
                let selected = MOUSE_BROADCAST_TARGETS.lock().unwrap().clone();
                if !selected.is_empty() {
                    for target in sessions::get_sessions() {
                        if !target.is_default() || Arc::ptr_eq(&session, &target) {
                            continue;
                        }
                        if !target.connection_round_state.lock().unwrap().is_connected() {
                            continue;
                        }
                        let peer_id = target.lc.read().unwrap().get_id().to_owned();
                        if !selected.contains(&peer_id) {
                            continue;
                        }
                        target.send_mouse(mask, x, y, alt, ctrl, shift, command);
                    }
                }
            }""")

replace_once(dart,
    """import 'dart:async';
""",
    """import 'dart:async';
import 'dart:convert';
""")

replace_once(dart,
    """  static const _mouseBroadcastKey = 'mouse-broadcast-source';""",
    """  static const _mouseBroadcastKey = 'mouse-broadcast-source';
  static const _mouseBroadcastTargetsKey = 'mouse-broadcast-targets';""")

replace_once(dart,
    """  @override
  void initState() {""",
    """
  /// Choose exactly which connected remote-control peers receive clicks.
  /// The Rust backend owns the shared selection across RustDesk windows.
  List<String> _getMouseBroadcastPeers() {
    try {
      final value = bind.mainGetLocalOption(
          key: 'mouse-broadcast-peers:${sessionId.toString()}');
      final decoded = jsonDecode(value);
      if (decoded is List) {
        return decoded.whereType<String>().toList()..sort();
      }
    } catch (e) {
      debugPrint('Cannot list multi-click peers: $e');
    }
    return <String>[];
  }

  Set<String> _getSelectedMouseBroadcastTargets() {
    try {
      final value =
          bind.mainGetLocalOption(key: _mouseBroadcastTargetsKey);
      final decoded = jsonDecode(value);
      if (decoded is List) {
        return decoded.whereType<String>().toSet();
      }
    } catch (e) {
      debugPrint('Cannot read multi-click targets: $e');
    }
    return <String>{};
  }

  Future<void> _showMouseBroadcastTargetsDialog() async {
    if (!mounted) return;
    final peers = _getMouseBroadcastPeers();
    final isCurrentSource =
        bind.mainGetLocalOption(key: _mouseBroadcastKey) ==
            sessionId.toString();
    final selected = isCurrentSource
        ? _getSelectedMouseBroadcastTargets().intersection(peers.toSet())
        : <String>{};

    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.devices, size: 22),
              SizedBox(width: 10),
              Text('멀티클릭 대상 선택'),
            ],
          ),
          content: SizedBox(
            width: 440,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('기준 창에서 조작할 때 입력을 받을 원격 기기를 선택하세요.'),
                const SizedBox(height: 8),
                Text(
                  '연결된 대상 ${peers.length}대 · 선택 ${selected.length}대',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                Row(
                  children: [
                    TextButton(
                      onPressed: peers.isEmpty ? null : () =>
                          setDialogState(() => selected.addAll(peers)),
                      child: const Text('전체 선택'),
                    ),
                    TextButton(
                      onPressed: selected.isEmpty ? null : () =>
                          setDialogState(selected.clear),
                      child: const Text('전체 해제'),
                    ),
                    const Spacer(),
                    IconButton(
                      icon: const Icon(Icons.refresh),
                      tooltip: '연결된 기기 새로고침',
                      onPressed: () => setDialogState(() {
                        final refreshed = _getMouseBroadcastPeers();
                        peers..clear()..addAll(refreshed);
                        selected.removeWhere((id) => !peers.contains(id));
                      }),
                    ),
                  ],
                ),
                const Divider(height: 12),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 290),
                  child: peers.isEmpty
                      ? const Padding(
                          padding: EdgeInsets.symmetric(vertical: 24),
                          child: Text(
                            '연결된 다른 원격 기기가 없습니다.\n'
                            '다른 RustDesk 원격창을 연결한 다음 새로고침하세요.',
                            textAlign: TextAlign.center,
                          ),
                        )
                      : ListView.builder(
                          shrinkWrap: true,
                          itemCount: peers.length,
                          itemBuilder: (context, index) {
                            final peer = peers[index];
                            return CheckboxListTile(
                              dense: true,
                              controlAffinity:
                                  ListTileControlAffinity.leading,
                              secondary:
                                  const Icon(Icons.desktop_windows_outlined),
                              title: Text(peer,
                                  overflow: TextOverflow.ellipsis),
                              subtitle: const Text('연결됨'),
                              value: selected.contains(peer),
                              onChanged: (checked) => setDialogState(() {
                                if (checked == true) {
                                  selected.add(peer);
                                } else {
                                  selected.remove(peer);
                                }
                              }),
                            );
                          },
                        ),
                ),
                const SizedBox(height: 10),
                const Text('선택한 기기에만 이동·좌/우 클릭을 전송합니다. '
                    '0대 선택 시 멀티클릭은 꺼집니다.'),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('취소'),
            ),
            FilledButton(
              onPressed: () {
                final enabled = selected.isNotEmpty;
                // Arm source first: changing source clears the previous targets.
                bind.mainSetLocalOption(
                    key: _mouseBroadcastKey,
                    value: enabled ? sessionId.toString() : '');
                bind.mainSetLocalOption(
                    key: _mouseBroadcastTargetsKey,
                    value: jsonEncode(selected.toList()));
                if (mounted) {
                  setState(() => _mouseBroadcastEnabled = enabled);
                }
                Navigator.of(dialogContext).pop();
              },
              child: Text(selected.isEmpty
                  ? '멀티클릭 끄기'
                  : '적용 (${selected.length}대)'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void initState() {""")

replace_once(dart,
    """              if (isWindows && !_ffi.inputModel.relativeMouseMode.value)
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
""",
    """              if (isWindows && !_ffi.inputModel.relativeMouseMode.value)
                Positioned(
                  bottom: 12,
                  right: 12,
                  child: Material(
                    color: Colors.transparent,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Tooltip(
                          message: '멀티클릭 켜기 또는 끄기',
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
                                      key: _mouseBroadcastKey) ==
                                  sessionId.toString();
                              if (active) {
                                bind.mainSetLocalOption(
                                    key: _mouseBroadcastKey, value: '');
                                if (mounted) {
                                  setState(() =>
                                      _mouseBroadcastEnabled = false);
                                }
                              } else {
                                _showMouseBroadcastTargetsDialog();
                              }
                            },
                          ),
                        ),
                        const SizedBox(width: 6),
                        Tooltip(
                          message: '멀티클릭 대상 선택',
                          child: FilledButton.tonalIcon(
                            onPressed: _showMouseBroadcastTargetsDialog,
                            icon: const Icon(Icons.tune, size: 18),
                            label: const Text('대상 선택'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
""")

replace_once(flutter_core,
    """impl FlutterHandler {
    /// Push an event to all the event queues.""",
    """impl FlutterHandler {
    /// Return the remote image rectangle in its own pixel coordinates.
    /// For a source tab use the display selected by that tab, when available.
    /// For a target use the current display from its remote peer information.
    pub(crate) fn mouse_broadcast_bounds(
        &self,
        ui_session: Option<&SessionID>,
    ) -> Option<(i32, i32, i32, i32)> {
        let info = self.peer_info.read().unwrap();
        let default_display = if info.current_display >= 0 {
            info.current_display as usize
        } else {
            0
        };
        let display_index = ui_session
            .and_then(|id| self.session_handlers.read().unwrap()
                .get(id)
                .and_then(|handler| handler.displays.first().copied()))
            .unwrap_or(default_display);
        let display = info.displays.get(display_index)?;
        if display.width <= 0 || display.height <= 0 {
            return None;
        }
        Some((display.x, display.y, display.width, display.height))
    }

    /// Push an event to all the event queues.""")

replace_once(flutter_core,
    """    fn switch_display(&self, display: &SwitchDisplay) {
        let resolutions = serialize_resolutions(&display.resolutions.resolutions);""",
    """    fn switch_display(&self, display: &SwitchDisplay) {
        // Refresh the actual pixel geometry when a phone rotates or changes
        // resolution. Mouse broadcast must not keep using login-time sizes.
        if display.display >= 0 {
            let mut peer_info = self.peer_info.write().unwrap();
            if let Some(current) = peer_info.displays.get_mut(display.display as usize) {
                current.x = display.x;
                current.y = display.y;
                current.width = display.width;
                current.height = display.height;
            }
        }
        let resolutions = serialize_resolutions(&display.resolutions.resolutions);""")

replace_once(rust,
    """pub fn session_send_mouse(session_id: SessionID, msg: String) {""",
    """/// Map one coordinate from the source peer display to the corresponding
/// proportional position of a target display. Use 64-bit arithmetic to avoid
/// multiplication overflow and clamp to the visible image boundary.
fn mouse_broadcast_map_axis(
    pos: i32, source_origin: i32, source_len: i32,
    target_origin: i32, target_len: i32,
) -> i32 {
    if source_len <= 1 || target_len <= 1 {
        return target_origin;
    }
    let src_range = (source_len - 1) as i64;
    let dst_range = (target_len - 1) as i64;
    let offset = (pos as i64 - source_origin as i64).clamp(0, src_range);
    let scaled = (offset * dst_range + src_range / 2) / src_range;
    (target_origin as i64 + scaled).clamp(i32::MIN as i64, i32::MAX as i64) as i32
}

pub fn session_send_mouse(session_id: SessionID, msg: String) {""")

replace_once(rust,
    """                let selected = MOUSE_BROADCAST_TARGETS.lock().unwrap().clone();
                if !selected.is_empty() {
                    for target in sessions::get_sessions() {""",
    """                let selected = MOUSE_BROADCAST_TARGETS.lock().unwrap().clone();
                if !selected.is_empty() {
                    let source_bounds = session.ui_handler
                        .mouse_broadcast_bounds(Some(&session_id));
                    for target in sessions::get_sessions() {""")

replace_once(rust,
    """                        if !selected.contains(&peer_id) {
                            continue;
                        }
                        target.send_mouse(mask, x, y, alt, ctrl, shift, command);""",
    """                        if !selected.contains(&peer_id) {
                            continue;
                        }
                        // Skip targets without valid display information rather
                        // than clicking at an unverified/wrong location.
                        let (Some((sx, sy, sw, sh)), Some((tx, ty, tw, th))) =
                            (source_bounds, target.ui_handler.mouse_broadcast_bounds(None))
                        else {
                            continue;
                        };
                        // Flutter sends down/up with x=y=0; they click at the
                        // last synchronized cursor location. Scale move ONLY.
                        let (dst_x, dst_y) = if regular_move {
                            (
                                mouse_broadcast_map_axis(x, sx, sw, tx, tw),
                                mouse_broadcast_map_axis(y, sy, sh, ty, th),
                            )
                        } else {
                            (x, y)
                        };
                        target.send_mouse(mask, dst_x, dst_y, alt, ctrl, shift, command);""")

replace_once(dart,
    """  FFI get ffi => (_lastState.value! as _RemotePageState)._ffi;""",
    """  FFI get ffi => (_lastState.value! as _RemotePageState)._ffi;

  /// Entry point for the compact multi-click control in the window title bar.
  Future<void> showMouseBroadcastTargetPicker() async {
    final state = _lastState.value;
    if (state is _RemotePageState && state.mounted) {
      await state._showMouseBroadcastTargetsDialog();
    }
  }

  bool get isMouseBroadcastSource {
    final state = _lastState.value;
    if (state is! _RemotePageState || !state.mounted) return false;
    return bind.mainGetLocalOption(key: 'mouse-broadcast-source') ==
        state.sessionId.toString();
  }""")

replace_once(dart,
    """              if (isWindows && !_ffi.inputModel.relativeMouseMode.value)
                Positioned(
                  bottom: 12,
                  right: 12,
                  child: Material(
                    color: Colors.transparent,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Tooltip(
                          message: '멀티클릭 켜기 또는 끄기',
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
                                      key: _mouseBroadcastKey) ==
                                  sessionId.toString();
                              if (active) {
                                bind.mainSetLocalOption(
                                    key: _mouseBroadcastKey, value: '');
                                if (mounted) {
                                  setState(() =>
                                      _mouseBroadcastEnabled = false);
                                }
                              } else {
                                _showMouseBroadcastTargetsDialog();
                              }
                            },
                          ),
                        ),
                        const SizedBox(width: 6),
                        Tooltip(
                          message: '멀티클릭 대상 선택',
                          child: FilledButton.tonalIcon(
                            onPressed: _showMouseBroadcastTargetsDialog,
                            icon: const Icon(Icons.tune, size: 18),
                            label: const Text('대상 선택'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
""",
    """""")

replace_once(dart,
    """  Timer? _mouseBroadcastTimer;
  bool _mouseBroadcastEnabled = false;
""",
    """""")

replace_once(dart,
    """    if (isWindows) {
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
""",
    """""")

replace_once(dart,
    """    _mouseBroadcastTimer?.cancel();
""",
    """""")

replace_once(dart,
    """                if (mounted) {
                  setState(() => _mouseBroadcastEnabled = enabled);
                }
""",
    """""")

replace_once(remote_tab,
    """            _RelativeMouseModeHint(tabController: tabController),
            const AddButton(),""",
    """            _MouseBroadcastTitleButton(tabController: tabController),
            _RelativeMouseModeHint(tabController: tabController),
            const AddButton(),""")

replace_once(remote_tab,
    """/// A widget that displays a hint in the tab bar when relative mouse mode is active.""",
    """/// Small multi-click selector beside New Connection and window controls.
/// The currently selected remote tab determines the broadcasting source.
class _MouseBroadcastTitleButton extends StatefulWidget {
  final DesktopTabController tabController;

  const _MouseBroadcastTitleButton({Key? key, required this.tabController})
      : super(key: key);

  @override
  State<_MouseBroadcastTitleButton> createState() =>
      _MouseBroadcastTitleButtonState();
}

class _MouseBroadcastTitleButtonState
    extends State<_MouseBroadcastTitleButton> {
  Timer? _statusTimer;
  bool _lastActive = false;

  RemotePage? get _selectedRemotePage {
    final state = widget.tabController.state.value;
    if (state.tabs.isEmpty || state.selected >= state.tabs.length) return null;
    final selected = state.selectedTabInfo.page;
    return selected is RemotePage ? selected : null;
  }

  @override
  void initState() {
    super.initState();
    if (isWindows) {
      _statusTimer = Timer.periodic(const Duration(milliseconds: 600), (_) {
        if (!mounted) return;
        final active = _selectedRemotePage?.isMouseBroadcastSource ?? false;
        if (active != _lastActive) {
          setState(() => _lastActive = active);
        }
      });
    }
  }

  @override
  void dispose() {
    _statusTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!isWindows) return const SizedBox.shrink();
    return Obx(() {
      final remote = _selectedRemotePage;
      if (remote == null) return const SizedBox.shrink();
      final active = remote.isMouseBroadcastSource;
      return Tooltip(
        message: active ? '멀티클릭 ON · 대상 기기 변경' : '멀티클릭 대상 선택',
        child: IconButton(
          icon: Icon(Icons.mouse,
              size: 18, color: active ? Colors.deepOrange : null),
          splashRadius: 18,
          padding: EdgeInsets.zero,
          constraints: const BoxConstraints(minWidth: 34, minHeight: 28),
          onPressed: () async {
            await remote.showMouseBroadcastTargetPicker();
            if (mounted) setState(() {});
          },
        ),
      );
    });
  }
}

/// A widget that displays a hint in the tab bar when relative mouse mode is active.""")

replace_once(rust,
    """    if key == "mouse-broadcast-source" {
        let next = uuid::Uuid::parse_str(&value).ok();
        let mut source = MOUSE_BROADCAST_SOURCE.lock().unwrap();
        if *source != next {
            // Switching or disabling the source must never keep targets armed.
            MOUSE_BROADCAST_TARGETS.lock().unwrap().clear();
        }
        *source = next;
        return;
    }""",
    """    if key == "mouse-broadcast-source" {
        // OFF only disarms broadcasting; retain target IDs for the next ON.
        // Reopening the picker restores the user's previous selections.
        *MOUSE_BROADCAST_SOURCE.lock().unwrap() =
            uuid::Uuid::parse_str(&value).ok();
        return;
    }""")

replace_once(rust,
    """        // Only connected default remote-control peers can be selected.
        let connected: HashSet<String> = sessions::get_sessions()
            .into_iter()
            .filter(|s| s.is_default() &&
                s.connection_round_state.lock().unwrap().is_connected())
            .map(|s| s.lc.read().unwrap().get_id().to_owned())
            .collect();
        *MOUSE_BROADCAST_TARGETS.lock().unwrap() = requested
            .into_iter().filter(|id| connected.contains(id)).collect();""",
    """        // Preserve selections if a remote device temporarily disconnects.
        // Dispatch still checks the target is actually connected before sending.
        *MOUSE_BROADCAST_TARGETS.lock().unwrap() = requested
            .into_iter()
            .filter(|id| !id.trim().is_empty() && id.len() <= 256)
            .take(512)
            .collect();""")

replace_once(dart,
    """import 'dart:convert';
""",
    """import 'dart:convert';
import 'package:flutter/gestures.dart';
""")

replace_once(dart,
    """  bool get isMouseBroadcastSource {
    final state = _lastState.value;
    if (state is! _RemotePageState || !state.mounted) return false;
    return bind.mainGetLocalOption(key: 'mouse-broadcast-source') ==
        state.sessionId.toString();
  }""",
    """  bool get isMouseBroadcastSource {
    final state = _lastState.value;
    if (state is! _RemotePageState || !state.mounted) return false;
    return bind.mainGetLocalOption(key: 'mouse-broadcast-source') ==
        state.sessionId.toString();
  }

  /// Stop sending input without losing any selected remote device IDs.
  void stopMouseBroadcast() {
    if (isMouseBroadcastSource) {
      bind.mainSetLocalOption(key: 'mouse-broadcast-source', value: '');
    }
  }""")

replace_once(dart,
    """  Future<void> _showMouseBroadcastTargetsDialog() async {
    if (!mounted) return;
    final peers = _getMouseBroadcastPeers();
    final isCurrentSource =
        bind.mainGetLocalOption(key: _mouseBroadcastKey) ==
            sessionId.toString();
    final selected = isCurrentSource
        ? _getSelectedMouseBroadcastTargets().intersection(peers.toSet())
        : <String>{};

    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.devices, size: 22),
              SizedBox(width: 10),
              Text('멀티클릭 대상 선택'),
            ],
          ),
          content: SizedBox(
            width: 440,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('기준 창에서 조작할 때 입력을 받을 원격 기기를 선택하세요.'),
                const SizedBox(height: 8),
                Text(
                  '연결된 대상 ${peers.length}대 · 선택 ${selected.length}대',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                Row(
                  children: [
                    TextButton(
                      onPressed: peers.isEmpty ? null : () =>
                          setDialogState(() => selected.addAll(peers)),
                      child: const Text('전체 선택'),
                    ),
                    TextButton(
                      onPressed: selected.isEmpty ? null : () =>
                          setDialogState(selected.clear),
                      child: const Text('전체 해제'),
                    ),
                    const Spacer(),
                    IconButton(
                      icon: const Icon(Icons.refresh),
                      tooltip: '연결된 기기 새로고침',
                      onPressed: () => setDialogState(() {
                        final refreshed = _getMouseBroadcastPeers();
                        peers..clear()..addAll(refreshed);
                        selected.removeWhere((id) => !peers.contains(id));
                      }),
                    ),
                  ],
                ),
                const Divider(height: 12),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 290),
                  child: peers.isEmpty
                      ? const Padding(
                          padding: EdgeInsets.symmetric(vertical: 24),
                          child: Text(
                            '연결된 다른 원격 기기가 없습니다.\n'
                            '다른 RustDesk 원격창을 연결한 다음 새로고침하세요.',
                            textAlign: TextAlign.center,
                          ),
                        )
                      : ListView.builder(
                          shrinkWrap: true,
                          itemCount: peers.length,
                          itemBuilder: (context, index) {
                            final peer = peers[index];
                            return CheckboxListTile(
                              dense: true,
                              controlAffinity:
                                  ListTileControlAffinity.leading,
                              secondary:
                                  const Icon(Icons.desktop_windows_outlined),
                              title: Text(peer,
                                  overflow: TextOverflow.ellipsis),
                              subtitle: const Text('연결됨'),
                              value: selected.contains(peer),
                              onChanged: (checked) => setDialogState(() {
                                if (checked == true) {
                                  selected.add(peer);
                                } else {
                                  selected.remove(peer);
                                }
                              }),
                            );
                          },
                        ),
                ),
                const SizedBox(height: 10),
                const Text('선택한 기기에만 이동·좌/우 클릭을 전송합니다. '
                    '0대 선택 시 멀티클릭은 꺼집니다.'),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('취소'),
            ),
            FilledButton(
              onPressed: () {
                final enabled = selected.isNotEmpty;
                // Arm source first: changing source clears the previous targets.
                bind.mainSetLocalOption(
                    key: _mouseBroadcastKey,
                    value: enabled ? sessionId.toString() : '');
                bind.mainSetLocalOption(
                    key: _mouseBroadcastTargetsKey,
                    value: jsonEncode(selected.toList()));
                Navigator.of(dialogContext).pop();
              },
              child: Text(selected.isEmpty
                  ? '멀티클릭 끄기'
                  : '적용 (${selected.length}대)'),
            ),
          ],
        ),
      ),
    );
  }

""",
    """  Future<void> _showMouseBroadcastTargetsDialog() async {
    if (!mounted) return;
    // Remember selections independently from whether broadcasting is ON.
    final connected = _getMouseBroadcastPeers().toSet();
    final selected = _getSelectedMouseBroadcastTargets();
    // Show previously selected offline devices too, so they are never lost.
    final peers = <String>{...connected, ...selected}.toList()..sort();
    final scrollController = ScrollController();

    void togglePeer(String peer, StateSetter update) {
      update(() {
        if (!selected.add(peer)) selected.remove(peer);
      });
    }

    try {
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => StatefulBuilder(
          builder: (context, setDialogState) {
            final theme = Theme.of(context);
            final smallButtonStyle = TextButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 6),
              minimumSize: const Size(0, 28),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              textStyle: const TextStyle(fontSize: 12),
            );
            return AlertDialog(
              title: const Text('멀티클릭'),
              titlePadding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
              contentPadding: const EdgeInsets.symmetric(horizontal: 20),
              actionsPadding: const EdgeInsets.fromLTRB(12, 4, 12, 10),
              content: SizedBox(
                width: 390,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('입력을 받을 원격 기기를 선택하세요.',
                        style: TextStyle(fontSize: 13)),
                    const SizedBox(height: 4),
                    Text('연결 ${connected.length}대 · 선택 ${selected.length}대',
                        style: theme.textTheme.bodySmall),
                    Row(
                      children: [
                        TextButton(
                          style: smallButtonStyle,
                          onPressed: connected.isEmpty
                              ? null
                              : () => setDialogState(() =>
                                  selected.addAll(connected)),
                          child: const Text('전체 선택'),
                        ),
                        TextButton(
                          style: smallButtonStyle,
                          onPressed: selected.isEmpty
                              ? null
                              : () => setDialogState(selected.clear),
                          child: const Text('전체 해제'),
                        ),
                        const Spacer(),
                        IconButton(
                          icon: const Icon(Icons.refresh, size: 18),
                          tooltip: '기기 목록 새로고침',
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(
                              minWidth: 30, minHeight: 30),
                          onPressed: () => setDialogState(() {
                            connected
                              ..clear()
                              ..addAll(_getMouseBroadcastPeers());
                            peers
                              ..clear()
                              ..addAll({...connected, ...selected});
                            peers.sort();
                          }),
                        ),
                      ],
                    ),
                    const Divider(height: 8),
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxHeight: 300),
                      child: peers.isEmpty
                          ? const Padding(
                              padding: EdgeInsets.symmetric(vertical: 18),
                              child: Text('다른 원격 기기를 연결한 뒤 새로고침하세요.'),
                            )
                          : ScrollConfiguration(
                              // Desktop Flutter defaults to wheel-only mouse
                              // scrolling. Also allow press-and-drag on rows.
                              behavior: const MaterialScrollBehavior().copyWith(
                                dragDevices: {
                                  PointerDeviceKind.mouse,
                                  PointerDeviceKind.touch,
                                  PointerDeviceKind.stylus,
                                  PointerDeviceKind.trackpad,
                                },
                              ),
                              child: Scrollbar(
                                controller: scrollController,
                                thumbVisibility: peers.length > 8,
                                child: ListView.builder(
                                  controller: scrollController,
                                  shrinkWrap: true,
                                  itemExtent: 36,
                                  physics: const ClampingScrollPhysics(),
                                  itemCount: peers.length,
                                  itemBuilder: (context, index) {
                                    final peer = peers[index];
                                    final alias = bind.mainGetPeerOptionSync(
                                            id: peer, key: 'alias')
                                        .trim();
                                    final online = connected.contains(peer);
                                    final checked = selected.contains(peer);
                                    return Material(
                                      color: checked
                                          ? theme.colorScheme.primary
                                              .withOpacity(0.06)
                                          : Colors.transparent,
                                      child: InkWell(
                                        onTap: () => togglePeer(
                                            peer, setDialogState),
                                        child: Row(
                                          children: [
                                            SizedBox(
                                              width: 32,
                                              child: Checkbox(
                                                value: checked,
                                                onChanged: (_) => togglePeer(
                                                    peer, setDialogState),
                                                materialTapTargetSize:
                                                    MaterialTapTargetSize
                                                        .shrinkWrap,
                                                visualDensity:
                                                    const VisualDensity(
                                                  horizontal: -4,
                                                  vertical: -4,
                                                ),
                                              ),
                                            ),
                                            const SizedBox(width: 6),
                                            Expanded(
                                              child: Text.rich(
                                                TextSpan(
                                                  children: [
                                                    TextSpan(
                                                      text: alias.isEmpty
                                                          ? peer
                                                          : alias,
                                                      style: const TextStyle(
                                                          fontWeight:
                                                              FontWeight.w600),
                                                    ),
                                                    if (alias.isNotEmpty)
                                                      TextSpan(
                                                        text: '  ·  $peer',
                                                        style: TextStyle(
                                                          fontSize: 10,
                                                          color: theme
                                                              .colorScheme
                                                              .onSurfaceVariant,
                                                        ),
                                                      ),
                                                    if (!online)
                                                      TextSpan(
                                                        text: '  (오프라인)',
                                                        style: TextStyle(
                                                          fontSize: 10,
                                                          color: theme
                                                              .colorScheme
                                                              .error,
                                                        ),
                                                      ),
                                                  ],
                                                ),
                                                maxLines: 1,
                                                overflow:
                                                    TextOverflow.ellipsis,
                                                style: const TextStyle(
                                                    fontSize: 12),
                                              ),
                                            ),
                                            const SizedBox(width: 6),
                                          ],
                                        ),
                                      ),
                                    );
                                  },
                                ),
                              ),
                            ),
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(dialogContext).pop(),
                  child: const Text('취소'),
                ),
                FilledButton(
                  onPressed: () {
                    final targetList = selected.toList()..sort();
                    bind.mainSetLocalOption(
                        key: _mouseBroadcastTargetsKey,
                        value: jsonEncode(targetList));
                    bind.mainSetLocalOption(
                        key: _mouseBroadcastKey,
                        value: selected.isNotEmpty
                            ? sessionId.toString()
                            : '');
                    Navigator.of(dialogContext).pop();
                  },
                  child: Text(selected.isEmpty
                      ? '끄기'
                      : '적용 (${selected.length}대)'),
                ),
              ],
            );
          },
        ),
      );
    } finally {
      scrollController.dispose();
    }
  }

""")

replace_once(remote_tab,
    """        message: active ? '멀티클릭 ON · 대상 기기 변경' : '멀티클릭 대상 선택',""",
    """        message: active ? '멀티클릭 ON · 클릭하면 OFF' : '멀티클릭 OFF · 대상 선택',""")

replace_once(remote_tab,
    """              size: 18, color: active ? Colors.deepOrange : null),""",
    """              size: 18, color: active ? Colors.red : null),""")

replace_once(remote_tab,
    """          onPressed: () async {
            await remote.showMouseBroadcastTargetPicker();
            if (mounted) setState(() {});
          },""",
    """          onPressed: () async {
            if (active) {
              // One click disarms, but Rust retains the chosen target IDs.
              remote.stopMouseBroadcast();
            } else {
              await remote.showMouseBroadcastTargetPicker();
            }
            if (mounted) setState(() {});
          },""")

print("Patched RustDesk with retained target selections, alias labels, and draggable compact list")
