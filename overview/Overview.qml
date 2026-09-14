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
    property int page: 0
    readonly property int columns: width < 900 ? 1 : 2
    readonly property int pageSize: columns * 2
    readonly property int pageCount: Math.max(1, Math.ceil(snapshot.workspaces.length / pageSize))
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
    onPageCountChanged: page = Math.min(page, pageCount - 1)
    Component.onCompleted: {
        const index = snapshot.workspaces.findIndex(w => w.active);
        page = Math.max(0, Math.floor(index / pageSize));
    }
    Rectangle { anchors.fill: parent; color: view.backgroundColor }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 18
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true
                Text { text: "Workspace overview"; color: view.foreground; font.pixelSize: 28 }
                Text { text: "Select a window or workspace · Swipe down or press Esc to close"; color: Qt.alpha(view.foreground, 0.75); font.pixelSize: 14 }
            }
            Button { text: "Close"; Accessible.name: "Close overview"; onClicked: view.dismiss() }
        }
        GridLayout {
            id: grid
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: view.columns
            rowSpacing: 18
            columnSpacing: 18
            Repeater {
                model: view.snapshot.workspaces.slice(view.page * view.pageSize, (view.page + 1) * view.pageSize)
                delegate: Rectangle {
                    id: group
                    required property var modelData
                    property int windowPage: 0
                    readonly property int windowPages: Math.max(1, Math.ceil(modelData.windows.length / 3))
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    Layout.minimumHeight: 0
                    color: Qt.lighter(view.backgroundColor, 1.08)
                    radius: 10
                    border.color: modelData.active ? view.accent : Qt.alpha(view.foreground, 0.25)
                    border.width: modelData.active ? 2 : 1
                    onWindowPagesChanged: windowPage = Math.min(windowPage, windowPages - 1)
                    Component.onCompleted: windowPage = Math.max(0, Math.floor(modelData.windows.findIndex(w => w.active) / 3))
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Button {
                                id: workspaceButton
                                Layout.fillWidth: true
                                text: "Workspace " + group.modelData.name + (group.modelData.active ? " · current" : "")
                                contentItem: Text { text: workspaceButton.text; textFormat: Text.PlainText; elide: Text.ElideRight; color: view.foreground; verticalAlignment: Text.AlignVCenter }
                                onClicked: view.selected("workspace", group.modelData.key)
                            }
                            Button { text: "‹"; Accessible.name: "Previous windows"; visible: group.windowPages > 1; enabled: group.windowPage > 0; onClicked: group.windowPage-- }
                            Text { text: (group.windowPage + 1) + "/" + group.windowPages; visible: group.windowPages > 1; color: view.foreground }
                            Button { text: "›"; Accessible.name: "Next windows"; visible: group.windowPages > 1; enabled: group.windowPage + 1 < group.windowPages; onClicked: group.windowPage++ }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 10
                            Repeater {
                                model: group.modelData.windows.slice(group.windowPage * 3, (group.windowPage + 1) * 3)
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
                            Button {
                                visible: group.modelData.windows.length === 0
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                text: "Empty workspace · select to switch"
                                onClicked: view.selected("workspace", group.modelData.key)
                            }
                        }
                    }
                }
            }
        }
        Text { visible: !view.snapshot.workspaces.length; text: "No workspaces available on this monitor"; color: view.foreground }
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            Button { objectName: "previousPage"; text: "‹ Previous"; enabled: view.page > 0; onClicked: view.page-- }
            Text { text: (view.page + 1) + " / " + view.pageCount; color: view.foreground }
            Button { objectName: "nextPage"; text: "Next ›"; enabled: view.page + 1 < view.pageCount; onClicked: view.page++ }
        }
    }
}
