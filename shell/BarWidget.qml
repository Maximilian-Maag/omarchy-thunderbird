import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Unread-mail count for the Omarchy bar, backed by omarchy-thunderbird-unread.
//
// The backend reads read-state straight from the Thunderbird profile's mbox stores
// (the X-Mozilla-Status Read bit), so the count is real and needs no extension or
// running connection. The widget polls it on a timer, refreshes on demand via IPC,
// and left-click opens/focuses Thunderbird.
BarWidget {
  id: root
  moduleName: "Maximilian-Maag.thunderbird"

  property int unread: 0

  // nf-fa-envelope. Nerd Font glyph, matching the bar's other icon widgets.
  readonly property string glyph: "\uf0e0"
  readonly property string label: unread > 0 ? glyph + " " + unread : glyph
  readonly property string tooltip: unread > 0
    ? unread + (unread === 1 ? " unread message" : " unread messages")
    : "No unread messages"

  function refresh() {
    if (!countProc.running) countProc.running = true
  }

  function openThunderbird() {
    if (root.bar) root.bar.run("thunderbird")
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  IpcHandler {
    target: "Maximilian-Maag.thunderbird"

    function refresh(): void {
      root.broadcast("refresh")
    }
  }

  Process {
    id: countProc
    command: ["omarchy-thunderbird-unread", "--quiet"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var parsed = parseInt(String(text || "").trim(), 10)
        root.unread = isNaN(parsed) || parsed < 0 ? 0 : parsed
      }
    }
  }

  Timer {
    interval: 30000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.label
    labelVisible: false
    active: root.unread > 0
    useActiveColor: false
    tooltipText: root.tooltip
    horizontalMargin: 8.5
    verticalPadding: 8.5
    onPressed: function(mouse) { root.openThunderbird() }
  }
}
