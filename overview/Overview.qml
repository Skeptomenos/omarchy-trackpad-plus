pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

FocusScope {
    id: view
    property var snapshot: ({workspaces: []})
    property var sourceFor: function(entry) { return null; }
    property bool captureEnabled: true
    property color foreground: "#ded4b8"
    property color backgroundColor: "#293238"
    property color accent: "#80b9b2"
    readonly property var activeWorkspace: snapshot.workspaces.find(w => w.active) || null
    readonly property string activeKey: activeWorkspace ? activeWorkspace.key : ""
    readonly property int windowCount: activeWorkspace ? activeWorkspace.windows.length : 0
    readonly property int windowsPerPage: 6
    property int windowPage: 0
    readonly property int windowPageCount: Math.max(1, Math.ceil(windowCount / windowsPerPage))
    readonly property int columns: width < 900 ? 2 : 3
    onActiveKeyChanged: {
        windowPage = activeWorkspace ? Math.max(0, Math.floor(activeWorkspace.windows.findIndex(w => w.active) / windowsPerPage)) : 0;
        revealWorkspace.restart();
    }
    onWindowPageCountChanged: windowPage = Math.min(windowPage, windowPageCount - 1)
    property int inFlight: 0
    property var cards: []
    property int readyCount: 0
    signal dismiss()
    signal selected(string kind, string key)
    focus: true
    Keys.onEscapePressed: dismiss()
    // Tab follows all visible controls; arrows move within the same order.
    Keys.onPressed: event => {
        if (event.key === Qt.Key_Left || event.key === Qt.Key_Up) {
            const item = activeFocusItem();
            if (item) moveFocus(item, false);
            event.accepted = true;
        } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Down) {
            const item = activeFocusItem();
            if (item) moveFocus(item, true);
            event.accepted = true;
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            const item = activeFocusItem();
            if (item && item.enabled && typeof item.clicked === "function") item.clicked();
            event.accepted = true;
        }
    }
    function moveFocus(item, forward) {
        let next = item.nextItemInFocusChain(forward);
        while (next && next !== item) {
            if (next.visible && next.enabled && next.activeFocusOnTab) { next.forceActiveFocus(); return; }
            next = next.nextItemInFocusChain(forward);
        }
    }
    function activeFocusItem() { return Window.window ? Window.window.activeFocusItem : null; }
    function enqueue(card) { cards = cards.concat([card]); pump.start(); }
    function startQueued() {
        const live = cards.filter(card => card && card.captureState !== undefined && card.captureState !== "retired");
        let active = live.filter(card => card.captureState === "capturing").length;
        for (let card of live) {
            if (active >= 2) break;
            if (card.captureState !== "waiting") continue;
            card.beginCapture();
            if (card.captureState === "capturing") active++;
        }
        cards = live;
        inFlight = active;
        readyCount = live.filter(card => card.captureState === "ready").length;
        pump.running = active > 0 || live.some(card => card.captureState === "waiting");
    }
    Timer { id: pump; interval: 30; repeat: true; onTriggered: view.startQueued() }
    onSnapshotChanged: pump.start()
    Timer {
        id: revealWorkspace
        interval: 0
        onTriggered: {
            const index = view.snapshot.workspaces.findIndex(w => w.active);
            if (index >= 0) strip.positionViewAtIndex(index, ListView.Contain);
        }
    }
    Component.onCompleted: revealWorkspace.start()
    Rectangle { anchors.fill: parent; color: view.backgroundColor }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 18
        ListView {
            id: strip
            objectName: "workspaceStrip"
            Layout.fillWidth: true
            Layout.maximumWidth: 1320
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredHeight: Math.min(160, view.height * 0.23)
            orientation: ListView.Horizontal
            spacing: 12
            clip: true
            // Keep lightweight buttons in the focus chain even beyond the viewport.
            // Their preview Loaders still unload captures as they scroll offscreen.
            cacheBuffer: Math.max(0, contentWidth)
            boundsBehavior: Flickable.StopAtBounds
            model: view.snapshot.workspaces
            readonly property real cardWidth: Math.max(136, Math.min(208,
                (width - 12 * (Math.min(count, 6) - 1)) / Math.max(1, Math.min(count, 6))))
            ScrollBar.horizontal: ScrollBar { policy: strip.contentWidth > strip.width ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
            delegate: Button {
                id: workspace
                required property var modelData
                required property int index
                onActiveFocusChanged: { if (activeFocus) strip.positionViewAtIndex(index, ListView.Contain); }
                objectName: "workspace-" + modelData.key
                width: strip.cardWidth
                height: strip.height - 12
                padding: 8
                hoverEnabled: true
                Accessible.name: "Workspace " + modelData.name + (modelData.active ? ", current" : "")
                onClicked: view.selected("workspace", modelData.key)
                background: Rectangle {
                    radius: 8
                    color: workspace.modelData.active ? Qt.lighter(view.backgroundColor, 1.3) : Qt.lighter(view.backgroundColor, 1.08)
                    border.width: workspace.modelData.active || workspace.hovered || workspace.activeFocus ? 2 : 1
                    border.color: workspace.modelData.active || workspace.hovered || workspace.activeFocus ? view.accent : Qt.alpha(view.foreground, 0.2)
                }
                contentItem: ColumnLayout {
                    spacing: 6
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        // A representative window summarizes each workspace. Only
                        // on-screen thumbnails retain captures, including while scrolling.
                        Loader {
                            anchors.fill: parent
                            active: workspace.modelData.windows.length > 0 && workspace.x + workspace.width > strip.contentX
                                && workspace.x < strip.contentX + strip.width
                            sourceComponent: WindowCard {
                                entry: workspace.modelData.windows.find(w => w.active) || workspace.modelData.windows[0]
                                source: view.sourceFor(entry)
                                captureEnabled: view.captureEnabled
                                compact: true
                                enabled: false
                                foreground: view.foreground
                                backgroundColor: view.backgroundColor
                                accent: view.accent
                                onQueued: card => view.enqueue(card)
                            }
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: workspace.modelData.windows.length === 0
                            text: "Empty"
                            color: Qt.alpha(view.foreground, 0.5)
                            font.pixelSize: 13
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Workspace " + workspace.modelData.name + "  ·  " + workspace.modelData.windows.length
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        horizontalAlignment: Text.AlignHCenter
                        color: view.foreground
                        font.pixelSize: 13
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Qt.alpha(view.foreground, 0.16) }
        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: view.activeWorkspace ? "Workspace " + view.activeWorkspace.name : "No ordinary workspace selected"
                textFormat: Text.PlainText
                color: view.foreground
                font.pixelSize: 22
                elide: Text.ElideRight
            }
            Button { text: "Close"; Accessible.name: "Close overview"; onClicked: view.dismiss() }
        }
        GridLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: view.columns
            rowSpacing: 18
            columnSpacing: 18
            Repeater {
                model: view.activeWorkspace ? view.activeWorkspace.windows.slice(view.windowPage * view.windowsPerPage, (view.windowPage + 1) * view.windowsPerPage) : []
                delegate: WindowCard {
                    required property var modelData
                    entry: modelData
                    source: view.sourceFor(entry)
                    captureEnabled: view.captureEnabled
                    foreground: view.foreground
                    backgroundColor: view.backgroundColor
                    accent: view.accent
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    Layout.minimumHeight: 0
                    onQueued: card => view.enqueue(card)
                    onClicked: view.selected("window", entry.key)
                }
            }
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: view.windowCount === 0
                Text {
                    objectName: "emptyWorkspace"
                    anchors.centerIn: parent
                    text: view.activeWorkspace ? "This workspace is empty" : "Select a workspace above"
                    visible: parent.visible
                    color: Qt.alpha(view.foreground, 0.65)
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: "Choose a workspace above · Select a window to enter · Esc to close"; color: Qt.alpha(view.foreground, 0.65); font.pixelSize: 12; wrapMode: Text.WordWrap }
            Button { objectName: "previousWindows"; text: "‹"; Accessible.name: "Previous windows"; visible: view.windowPageCount > 1; enabled: view.windowPage > 0; onClicked: view.windowPage-- }
            Text { text: (view.windowPage + 1) + " / " + view.windowPageCount; visible: view.windowPageCount > 1; color: view.foreground }
            Button { objectName: "nextWindows"; text: "›"; Accessible.name: "Next windows"; visible: view.windowPageCount > 1; enabled: view.windowPage + 1 < view.windowPageCount; onClicked: view.windowPage++ }
        }
    }
}
