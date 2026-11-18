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

print("Patched RustDesk with select-target multi-click panel")
