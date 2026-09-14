import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import "Model.js" as Model

ShellRoot {
    id: root
    property var snapshot: ({workspaces: []})
    property var lifetimes: []
    property int serial: 0
    property int monitorId: -1
    property string monitorName: ""
    property int priorWorkspace: 0
    property var priorWindow: null
    property var activation: null
    property color foreground: "#ded4b8"
    property color backgroundColor: "#293238"
    property color accent: "#80b9b2"

    function rebuild() {
        if (!session.opened && !session.pending) return;
        const monitors = Hyprland.monitors.values;
        if (!monitors.some(m => m.id === monitorId)) { session.dismiss("monitor-removed"); return; }
        const live = Hyprland.toplevels.values;
        lifetimes = lifetimes.filter(record => live.indexOf(record.source) >= 0);
        const records = new Map(lifetimes.map(record => [record.source, record]));
        const windows = live.map(w => {
            let record = records.get(w);
            if (!record) { record = {source: w, token: String(++serial)}; lifetimes.push(record); }
            const raw = w.lastIpcObject || {};
            return {address: w.address, pid: raw.pid, token: record.token,
                workspace: {id: w.workspace ? w.workspace.id : 0},
                monitor: w.monitor ? w.monitor.id : null, hidden: raw.hidden, mapped: raw.mapped,
                title: w.title, class: raw.class};
        });
        const next = Model.buildSnapshot({session: session.sessionIdentity, monitorId: monitorId,
            monitors: monitors.map(m => ({id: m.id, name: m.name})),
            workspaces: Hyprland.workspaces.values.map(w => ({id: w.id, name: w.name,
                monitorID: w.monitor ? w.monitor.id : null})), windows: windows,
            activeAddress: priorWindow ? priorWindow.address : "",
            activeWorkspaceId: priorWorkspace});
        // Preserve live cards and their paging when a compositor event leaves
        // the overview model unchanged. Titles refresh on the next open.
        if (JSON.stringify(next) !== JSON.stringify(snapshot)) snapshot = next;
    }
    function sourceFor(entry) {
        const record = lifetimes.find(r => r.token === entry.token);
        return record && record.source ? record.source.wayland : null;
    }
    function select(kind, key) {
        rebuild();
        const entry = Model.resolveSelection(snapshot, {kind: kind, key: key});
        if (!entry) return;
        const record = kind === "window" ? lifetimes.find(r => r.token === entry.token) : null;
        activation = {kind: kind, entry: entry, source: record ? record.source : null};
        session.dismiss("selection");
        activateDelay.restart();
    }
    Session {
        id: session
        onWillOpen: {
            activateDelay.stop();
            root.activation = null;
            const monitor = Hyprland.focusedMonitor;
            if (!monitor || !Quickshell.screens.some(s => s.name === monitor.name)) {
                session.dismiss("no-monitor"); return;
            }
            root.monitorId = monitor.id;
            root.monitorName = monitor.name;
            root.priorWorkspace = Hyprland.focusedWorkspace ? Hyprland.focusedWorkspace.id : 0;
            root.priorWindow = Hyprland.activeToplevel;
            root.rebuild();
            Hyprland.refreshMonitors();
            Hyprland.refreshWorkspaces();
            Hyprland.refreshToplevels();
        }
        onClosed: reason => {
            refresh.stop();
            root.snapshot = {workspaces: []};
            if (["escape", "button", "closed"].indexOf(reason) >= 0) {
                root.activation = {kind: "restore", source: root.priorWindow};
                activateDelay.restart();
            } else if (reason !== "selection") root.activation = null;
            root.priorWindow = null;
        }
    }
    Timer {
        id: activateDelay
        interval: 50
        onTriggered: {
            const action = root.activation;
            root.activation = null;
            if (!action || session.opened || session.pending || session.lockState !== "unlocked") return;
            const monitor = Hyprland.monitors.values.find(m => m.id === root.monitorId);
            if (!monitor) return;
            if (action.kind === "workspace") {
                const workspace = Hyprland.workspaces.values.find(w => w.id === action.entry.id && w.monitor === monitor);
                if (workspace) workspace.activate();
                return;
            }
            const source = action.source;
            if (!source || Hyprland.toplevels.values.indexOf(source) < 0 || source.monitor !== monitor || !source.wayland) return;
            if (action.kind === "restore") {
                if (!Hyprland.focusedWorkspace || Hyprland.focusedWorkspace.id !== root.priorWorkspace
                    || !source.workspace || source.workspace.id !== root.priorWorkspace) return;
            } else {
                const raw = source.lastIpcObject || {};
                if (raw.hidden || raw.mapped === false || raw.pid !== action.entry.pid
                    || !source.workspace || source.workspace.id !== action.entry.workspaceId) return;
            }
            source.wayland.activate();
        }
    }
    Connections {
        target: Hyprland
        function onFocusedWorkspaceChanged() {
            if (session.opened && (!Hyprland.focusedWorkspace || Hyprland.focusedWorkspace.id !== root.priorWorkspace))
                session.dismiss("workspace-changed");
        }
        function onRawEvent(event) {
            if (!session.opened) return;
            if (/^(openwindow|closewindow|movewindow|workspace|createworkspace|destroyworkspace|monitor|changegroup|togglegroup)/.test(event.name))
                refresh.restart();
        }
    }
    Timer { id: refresh; interval: 100; onTriggered: root.rebuild() }
    FileView {
        path: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state") + "/omarchy/current/theme/shell.toml"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            const content = text();
            function color(key, fallback) {
                const match = content.match(new RegExp("^" + key + "\\s*=\\s*\"(#[0-9a-fA-F]{6})\"", "m"));
                return match ? match[1] : fallback;
            }
            root.foreground = color("text", "#ded4b8");
            root.backgroundColor = color("background", "#293238");
            root.accent = color("active-border", "#80b9b2");
        }
    }
    LazyLoader {
        active: session.opened
        component: PanelWindow {
            id: panel
            screen: Quickshell.screens.find(s => s.name === root.monitorName) || null
            anchors { top: true; bottom: true; left: true; right: true }
            exclusionMode: ExclusionMode.Ignore
            color: root.backgroundColor
            WlrLayershell.namespace: "trackpad-plus-overview"
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
            Overview {
                id: overview
                anchors.fill: parent
                snapshot: root.snapshot
                sourceFor: root.sourceFor
                foreground: root.foreground
                backgroundColor: root.backgroundColor
                accent: root.accent
                onInFlightChanged: session.captures = inFlight
                onReadyCountChanged: { session.ready = readyCount; if (readyCount > 0 && session.mapped) session.rendered = true; }
                onDismiss: session.dismiss("escape")
                onSelected: (kind, key) => root.select(kind, key)
                Component.onCompleted: forceActiveFocus()
            }
            Connections {
                target: panel.contentItem.Window.window
                function onFrameSwapped() {
                    if (session.opened) { session.mapped = true; session.rendered = overview.readyCount > 0; session.result = session.rendered ? "rendered" : "opened"; }
                }
            }
        }
    }
}
