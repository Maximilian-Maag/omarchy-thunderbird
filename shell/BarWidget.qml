import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Omarchy comms widget: unread mail, plus the next calendar event in the tooltip.
//
// Backends read the real Thunderbird profile — omarchy-thunderbird-unread counts
// unread mail from the mbox read bit, omarchy-thunderbird-calendar lists upcoming
// events. The widget polls them on a timer and refreshes on demand via IPC; a click
// opens Thunderbird.
BarWidget {
  id: root
  moduleName: "Maximilian-Maag.thunderbird"

  property int unread: 0
  property string nextEvent: ""

  // nf-fa-envelope
  readonly property string glyph: "\uf0e0"
  readonly property string label: unread > 0 ? glyph + " " + unread : glyph
  readonly property string tooltip: {
    var parts = []
    parts.push(unread > 0
      ? unread + (unread === 1 ? " unread message" : " unread messages")
      : "No unread messages")
    if (nextEvent !== "") parts.push("next: " + nextEvent)
    return parts.join("  ·  ")
  }

  function refresh() {
    if (!countProc.running) countProc.running = true
    if (!calProc.running) calProc.running = true
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

  Process {
    id: calProc
    command: ["omarchy-thunderbird-calendar", "--json", "--days", "1"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var data = JSON.parse(String(text || "").trim())
          if (data.count > 0 && data.events.length > 0) {
            root.nextEvent = data.events[0].start + "  " + data.events[0].title
          } else {
            root.nextEvent = ""
          }
        } catch (e) {
          root.nextEvent = ""
        }
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
