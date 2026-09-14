#!/usr/bin/env python3
"""Live overview integration check using owned terminals; never saves images.

Requires an unlocked session and an existing inactive workspace on its monitor.
Temporarily opens the overview, focuses only its own fixtures, then restores focus.
"""
import argparse
import importlib.util
import json
import os
import signal
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location('overview_control', REPO / 'overview-control.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=5)
    result.check_returncode()
    return result.stdout.strip()


def hypr(name):
    return json.loads(command('hyprctl', '-j', name))


def evaluate(code):
    assert command('hyprctl', 'eval', code) == 'ok'


def wait_for(check, seconds=4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.025)
    raise AssertionError('Live overview check timed out')


# Inject observability only into a temporary copy, never the installed shell.
# Pixels are sampled in memory and restricted to our constant-title fixtures.
INSTRUMENT = r'''
    TestResult { id: pixels }
    function testCards() {
        let cards = [];
        function walk(item) {
            if (!item) return;
            if (item.captureState !== undefined) cards.push(item);
            for (let child of item.children || []) walk(child);
        }
        if (overlay.item) walk(overlay.item.contentItem);
        return cards;
    }
    function testOverview() {
        let found = null;
        function walk(item) {
            if (!item || found) return;
            if (item.cards !== undefined && item.snapshot !== undefined) { found = item; return; }
            for (let child of item.children || []) walk(child);
        }
        if (overlay.item) walk(overlay.item.contentItem);
        return found;
    }
    function testGroup(address) {
        const overview = root.testOverview();
        let found = null;
        function walk(item) {
            if (!item || found) return;
            if (item.windowPage !== undefined && item.modelData && item.modelData.windows
                && item.modelData.windows.some(window => window.address === address)) { found = item; return; }
            for (let child of item.children || []) walk(child);
        }
        walk(overview);
        return found;
    }
    IpcHandler {
        target: "overviewCheck"
        function fixture(address: string): string {
            const card = root.testCards().find(c => c.entry.address === address);
            if (!card) return "not-visible";
            return card.captureState;
        }
        function pixelsOk(address: string): bool {
            const card = root.testCards().find(c => c.entry.address === address);
            if (!card || card.captureState !== "ready") return false;
            const image = pixels.grabImage(card);
            let low = 255, high = 0;
            // Exclude borders, footer title and controls from the contrast check.
            for (let row = 2; row < 32; row++) for (let col = 2; col < 38; col++) {
                const x = Math.floor(image.width * col / 40), y = Math.floor(image.height * row / 40);
                const value = (image.red(x,y) + image.green(x,y) + image.blue(x,y)) / 3;
                low = Math.min(low,value); high = Math.max(high,value);
            }
            return high - low > 80;
        }
        function selectFixture(address: string): bool {
            const entry = root.snapshot.workspaces.reduce((all, w) => all.concat(w.windows), []).find(w => w.address === address);
            if (!entry) return false;
            root.select("window", entry.key);
            return true;
        }
        function selectWorkspace(id: int): bool {
            const workspace = root.snapshot.workspaces.find(w => w.id === id);
            if (!workspace) return false;
            root.select("workspace", workspace.key);
            return true;
        }
        function setWindowPage(address: string, page: int): string {
            const group = root.testGroup(address);
            if (!group || group.windowPages <= page) return "unavailable";
            group.windowPage = page;
            return JSON.stringify({group: String(group), page: group.windowPage});
        }
        function cardAndPage(cardAddress: string, groupAddress: string): string {
            const card = root.testCards().find(c => c.entry.address === cardAddress);
            const group = root.testGroup(groupAddress);
            if (!card || !group) return "unavailable";
            return JSON.stringify({card: String(card), capture: card.captureState,
                group: String(group), page: group.windowPage});
        }
        function rebuildNoop(cardAddress: string, groupAddress: string): string {
            root.rebuild();
            return cardAndPage(cardAddress, groupAddress);
        }
    }
}
'''


def usage(pid):
    data = Path('/proc', str(pid), 'status').read_text()
    rss = next(int(line.split()[1]) for line in data.splitlines() if line.startswith('VmRSS:'))
    return dict(rssKiB=rss, fds=len(list(Path('/proc', str(pid), 'fd').iterdir())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycles', type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.cycles <= 100:
        parser.error('cycles must be 0–100')
    assert command('omarchy-shell', 'lock', 'isLocked') == 'false'
    prior = hypr('activewindow').get('address')
    original = hypr('activeworkspace')
    other = next(w for w in hypr('workspaces') if w['id'] > 0 and w['id'] != original['id'] and w['monitor'] == original['monitor'])
    owned = []
    with tempfile.TemporaryDirectory(prefix='trackpad-overview-live-') as directory:
        base = Path(directory)
        shutil.copytree(REPO / 'overview', base / 'overview')
        shutil.copy2(REPO / 'manifest.json', base / 'manifest.json')
        shell = base / 'overview/shell.qml'
        source = shell.read_text().replace('import QtQuick\n', 'import QtQuick\nimport QtTest\n', 1)
        source = source.replace('    LazyLoader {', '    LazyLoader {\n        id: overlay')
        shell.write_text(source.rstrip()[:-1] + INSTRUMENT)
        companion = control.Controller(base)
        try:
            title_files = []
            for index in range(5):
                title_file = base / ('fixture-title-' + str(index))
                title_file.write_text('Trackpad Plus overview check')
                title_files.append(title_file)
                fixture_program = (
                    'from pathlib import Path\nimport time\n'
                    + 'path = Path(' + repr(str(title_file)) + ')\n'
                    + 'print("Trackpad Plus live preview check\\n" * 30, flush=True)\n'
                    + 'previous = None\nwhile True:\n'
                    + '    title = path.read_text().strip()\n'
                    + '    if title != previous:\n'
                    + '        print("\\x1b]2;" + title + "\\x07", flush=True)\n'
                    + '        previous = title\n'
                    + '    time.sleep(.05)\n')
                owned.append(subprocess.Popen(['foot', '--config=/dev/null', '--log-no-syslog', '--log-level=none',
                    '--title=Trackpad Plus overview check', '--hold', 'python3', '-c', fixture_program],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0))))
            fixtures = wait_for(lambda: (windows if len(windows := [w for w in hypr('clients') if w['pid'] in [p.pid for p in owned]]) == 5 else None))
            first, second = fixtures[:2]
            evaluate('hl.dispatch(hl.dsp.window.move({workspace="%d",window="address:%s",follow=false}))' % (other['id'], second['address']))
            evaluate('hl.dispatch(hl.dsp.focus({window="address:%s"}))' % first['address'])
            time.sleep(.25)
            begin = time.monotonic()
            reply = companion.execute('open')
            pid = reply['pid']
            wait_for(lambda: companion.execute('status')['rendered'])
            cold = round((time.monotonic() - begin) * 1000)
            ipc = lambda method, *values: command('qs', 'ipc', '--pid', str(pid), 'call', 'overviewCheck', method, *map(str, values))
            for fixture in (first, second):
                wait_for(lambda: ipc('fixture', fixture['address']) == 'ready')
                assert ipc('pixelsOk', fixture['address']) == 'true', 'Preview has no contrasting application pixels'
            assert hypr('activeworkspace')['id'] == original['id'], 'Capturing changed the active workspace'
            # Keep four owned windows on the original workspace, select its
            # second page, then prove an OSC title change and a no-op rebuild do
            # not replace that page or the ready card on the other workspace.
            page = json.loads(ipc('setWindowPage', first['address'], 1))
            assert page['page'] == 1, 'Fixture workspace needs a second window page'
            before_title = json.loads(ipc('cardAndPage', second['address'], first['address']))
            assert before_title['page'] == 1 and before_title['capture'] == 'ready'
            assert json.loads(ipc('rebuildNoop', second['address'], first['address'])) == before_title, 'No-op rebuild replaced the visible card or page'
            title_files[0].write_text('Trackpad Plus overview title update')
            wait_for(lambda: next(window for window in hypr('clients') if window['pid'] == owned[0].pid)['title'] == 'Trackpad Plus overview title update')
            time.sleep(.25)
            after_title = json.loads(ipc('cardAndPage', second['address'], first['address']))
            assert after_title == before_title, 'Title-only update replaced the visible card or page'
            print('PASS: title and no-op updates preserve ready capture and window page')
            companion.execute('close')
            evaluate('hl.dispatch(hl.dsp.window.fullscreen({window="address:%s",mode="fullscreen"}))' % first['address'])
            time.sleep(.4)
            companion.execute('open')
            wait_for(lambda: ipc('fixture', first['address']) == 'ready')
            assert ipc('pixelsOk', first['address']) == 'true', 'Fullscreen preview is blank'
            companion.execute('close')
            evaluate('hl.dispatch(hl.dsp.window.fullscreen({window="address:%s",mode="fullscreen"}))' % first['address'])
            companion.execute('close')
            wait_for(lambda: hypr('activewindow').get('address') == first['address'])
            assert not companion.execute('status')['mapped']
            companion.execute('open')
            wait_for(lambda: companion.execute('status')['rendered'])
            assert ipc('selectFixture', second['address']) == 'true'
            wait_for(lambda: hypr('activewindow').get('address') == second['address'])
            assert hypr('activeworkspace')['id'] == other['id']
            companion.execute('open')
            wait_for(lambda: companion.execute('status')['mapped'])
            assert ipc('selectWorkspace', original['id']) == 'true'
            wait_for(lambda: hypr('activeworkspace')['id'] == original['id'])
            companion.execute('open')
            wait_for(lambda: companion.execute('status')['mapped'])
            evaluate('hl.dispatch(hl.dsp.focus({workspace="%d"}))' % other['id'])
            wait_for(lambda: not companion.execute('status')['opened'])
            assert hypr('activeworkspace')['id'] == other['id']
            evaluate('hl.dispatch(hl.dsp.focus({workspace="%d"}))' % original['id'])
            print('PASS: current/inactive workspace pixels, exact window selection, workspace selection, close/focus, external workspace change')
            before = usage(pid)
            peak = dict(before)
            latencies = []
            for _ in range(args.cycles):
                begin = time.monotonic()
                companion.execute('open')
                state = wait_for(lambda: (s if (s := companion.execute('status'))['rendered'] else None))
                assert state['captures'] <= 2
                latencies.append((time.monotonic() - begin) * 1000)
                current = usage(pid)
                peak = {key: max(peak[key], current[key]) for key in peak}
                companion.execute('close')
                state = companion.execute('status')
                assert not state['mapped'] and not state['rendered'] and state['captures'] == 0
                time.sleep(.06)
            if latencies:
                print(json.dumps(dict(cycles=args.cycles, coldMs=cold, warmMedianMs=round(statistics.median(latencies[:30])),
                    warmP95Ms=round(sorted(latencies[:30])[int(len(latencies[:30]) * .95) - 1]),
                    before=before, peak=peak, settled=usage(pid))))
            else:
                print(json.dumps(dict(coldMs=cold, usage=usage(pid))))
            # Kill only our verified companion; its observer must exit with it.
            children = Path('/proc', str(pid), 'task', str(pid), 'children')
            observer_pids = [int(value) for value in children.read_text().split()
                if str(base / 'overview/lock-watch.py').encode() in Path('/proc', value, 'cmdline').read_bytes()]
            os.kill(pid, signal.SIGKILL)
            wait_for(lambda: not companion.execute('status')['reachable'])
            wait_for(lambda: all(not Path('/proc', str(child)).exists()
                or Path('/proc', str(child), 'stat').read_text().split(') ')[1].startswith('Z ')
                for child in observer_pids))
            assert not companion.execute('start')['opened']
            assert not command('hyprctl', 'configerrors')
            print('PASS: forced companion exit releases observer; explicit restart stays hidden')

        finally:
            companion.execute('stop')
            for process in owned:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
            if command('omarchy-shell', 'lock', 'isLocked') == 'false':
                evaluate('hl.dispatch(hl.dsp.focus({workspace="%d"}))' % original['id'])
                if prior and any(w['address'] == prior for w in hypr('clients')):
                    evaluate('hl.dispatch(hl.dsp.focus({window="address:%s"}))' % prior)


if __name__ == '__main__':
    main()
