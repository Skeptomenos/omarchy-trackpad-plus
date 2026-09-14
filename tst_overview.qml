import QtQuick
import QtQuick.Controls
import QtTest
import "overview"

TestCase {
    id: test
    name: "Overview"
    visible: true
    when: windowShown
    width: 1100
    height: 850
    Component { id: component; Overview { width: 1100; height: 850; captureEnabled: false } }
    property var view
    function init() {
        let groups = [];
        for (let i = 1; i <= 7; i++) groups.push({key: "w" + i, id: i, name: String(i), active: i === 1,
            windows: i === 1 ? [{key: "a", title: "<b>Plain title</b>", appId: "app", active: true}] : []});
        view = createTemporaryObject(component, test, {snapshot: {workspaces: groups}});
        verify(view);
        view.forceActiveFocus();
        wait(30);
    }
    function test_paging() {
        compare(view.pageCount, 2);
        mouseClick(findChild(view, "nextPage"));
        compare(view.page, 1);
        mouseClick(findChild(view, "previousPage"));
        compare(view.page, 0);
        view.width = 700;
        compare(view.pageCount, 4);
    }
    function test_failed_capture_remains_selectable() {
        const spy = createTemporaryObject(spyComponent, test, {target: view, signalName: "selected"});
        const cards = [];
        function walk(item) {
            if (item.captureState !== undefined) cards.push(item);
            for (let child of item.children) walk(child);
        }
        walk(view);
        compare(cards.length, 1);
        tryCompare(cards[0], "captureState", "unavailable");
        mouseClick(cards[0]);
        compare(spy.count, 1);
        compare(spy.signalArguments[0][0], "window");
        compare(spy.signalArguments[0][1], "a");
        compare(view.inFlight, 0);
        cards[0].forceActiveFocus();
        keyClick(Qt.Key_Return);
        compare(spy.count, 2);
        keyClick(Qt.Key_Right);
        verify(!cards[0].activeFocus);
    }
    function test_escape() {
        const spy = createTemporaryObject(spyComponent, test, {target: view, signalName: "dismiss"});
        keyClick(Qt.Key_Escape);
        compare(spy.count, 1);
    }
    function test_removed_workspaces_clamp_page() {
        view.page = 1;
        view.snapshot = {workspaces: []};
        compare(view.page, 0);
        compare(view.pageCount, 1);
    }
    Component {
        id: pendingCard
        QtObject {
            property string captureState: "waiting"
            function beginCapture() { captureState = "capturing"; }
        }
    }
    function test_removed_inflight_cards_release_slots() {
        const first = pendingCard.createObject(test);
        const second = pendingCard.createObject(test);
        const third = createTemporaryObject(pendingCard, test);
        view.enqueue(first); view.enqueue(second); view.enqueue(third);
        tryCompare(view, "inFlight", 2);
        compare(third.captureState, "waiting");
        first.destroy(); second.destroy();
        tryCompare(third, "captureState", "capturing");
        compare(view.inFlight, 1);
        third.captureState = "ready";
        tryCompare(view, "inFlight", 0);
    }
    Component { id: spyComponent; SignalSpy {} }
}
