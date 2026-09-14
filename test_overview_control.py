#!/usr/bin/env python3
"""Lifecycle contract with owned fake Quickshell processes, no desktop access."""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

SPEC = importlib.util.spec_from_file_location('overview_control', Path(__file__).with_name('overview-control.py'))
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)

FAKE = '''#!/usr/bin/env python3
import json, os, socket, sys, time
from pathlib import Path
root = Path(os.environ['XDG_RUNTIME_DIR'])
if sys.argv[1] == 'ipc':
    pid = sys.argv[sys.argv.index('--pid')+1]
    with socket.socket(socket.AF_UNIX) as s:
        s.connect(str(root / ('fake-' + pid)))
        s.sendall(json.dumps(sys.argv[sys.argv.index('call')+2:]).encode())
        print(s.recv(65536).decode())
    sys.exit()
mode = os.environ.get('FAKE_MODE', '')
if mode == 'hang': time.sleep(30)
path = root / ('fake-' + str(os.getpid()))
s = socket.socket(socket.AF_UNIX); s.bind(str(path)); s.listen()
opened = False
while True:
    conn, _ = s.accept()
    with conn:
        args = json.loads(conn.recv(65536)); op = args[0]
        if mode == 'timeout': time.sleep(30)
        if mode == 'oversized': conn.sendall(b'x'*20000); continue
        if mode == 'malformed': conn.sendall(b'not-json'); continue
        if op != 'status' and args[1] != os.environ['TRACKPAD_OVERVIEW_TOKEN']:
            conn.sendall(b'{"error":"unauthorized"}'); continue
        if op == 'open': opened = True
        if op == 'toggle': opened = not opened
        if op == 'close': opened = False
        data = dict(protocol=1, version=os.environ['TRACKPAD_OVERVIEW_VERSION'], session=os.environ['TRACKPAD_OVERVIEW_SESSION'], pid=os.getpid(), instance='fake-instance', config=sys.argv[sys.argv.index('-p')+1], opened=opened, pending=False, lockState='unlocked', rendered=False, result='opened' if opened else 'hidden')
        if mode == 'wrong-version': data['version'] = 'wrong'
        if mode == 'wrong-session': data['session'] = 'wrong'
        conn.sendall(json.dumps(data).encode())
        if op == 'stop': sys.exit()
'''


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='overview tests ')
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'; self.runtime.mkdir(mode=0o700)
        self.base = self.root / 'install with spaces'; (self.base / 'overview').mkdir(parents=True)
        (self.base / 'overview/shell.qml').write_text('// fixture')
        (self.base / 'manifest.json').write_text('{"version":"2026.09.14.1"}')
        self.qs = self.root / 'fake qs'; self.qs.write_text(FAKE); self.qs.chmod(0o700)
        self.env = dict(os.environ, XDG_RUNTIME_DIR=str(self.runtime))
        self.controllers = []
        self.c = self.make()

    def make(self, **env):
        obj = control.Controller(self.base, self.runtime, 'compositor-session', str(self.qs), dict(self.env, **env), timeout=0.7)
        self.controllers.append(obj)
        return obj

    def tearDown(self):
        for c in self.controllers:
            try: c.execute('stop')
            except (control.ControlError, OSError): pass
            if c.last_spawn is not None:
                if c.last_spawn.poll() is None: c.last_spawn.kill()
                c.last_spawn.wait()
        self.temp.cleanup()

    def test_missing_inspection_and_close_never_launch(self):
        for op in ('status', 'close', 'stop'):
            self.assertFalse(self.c.execute(op)['reachable'])
        self.assertFalse(self.c.directory.exists())

    def test_start_is_capture_free_and_space_paths_work(self):
        first = self.c.execute('start')
        self.assertTrue(first['reachable'])
        self.assertFalse(first['opened'])
        self.assertFalse(first['rendered'])
        self.assertEqual(first['pid'], self.c.execute('start')['pid'])
        self.assertTrue(self.c.execute('open')['opened'])
        self.assertFalse(self.c.execute('close')['opened'])
        self.assertFalse(self.c.execute('stop')['reachable'])

    def test_concurrent_open_has_one_instance(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: self.make().execute('open'), range(2)))
        self.assertEqual(replies[0]['pid'], replies[1]['pid'])
        self.assertTrue(all(r['opened'] for r in replies))

    def test_wrong_token_cannot_mutate_or_stop_owned_process(self):
        reply = self.c.execute('start')
        record = json.loads(self.c.record_path.read_text()); record['token'] = '0'*64
        self.c.record_path.write_text(json.dumps(record))
        for op in ('close', 'stop', 'open'):
            with self.assertRaises(control.ControlError): self.c.execute(op)
        os.kill(reply['pid'], 0)
        # Restore the original record only for this test's owned cleanup.
        record['token'] = self.c.last_spawn_token
        self.c.record_path.write_text(json.dumps(record))

    def test_unrelated_pid_is_not_signaled(self):
        unrelated = subprocess.Popen(['sleep', '30'])
        try:
            self.c.execute('start')
            record = self.c.record_path.read_text()
            altered = json.loads(record); altered['pid'] = unrelated.pid
            self.c.record_path.write_text(json.dumps(altered))
            with self.assertRaises(control.ControlError): self.c.execute('stop')
            self.assertIsNone(unrelated.poll())
            self.c.record_path.write_text(record)
        finally:
            unrelated.terminate(); unrelated.wait()

    def test_stale_pid_record_recovers_only_explicit_start(self):
        self.c.execute('start'); self.c.execute('stop')
        self.c.record_path.write_text(json.dumps({'pid': 2147483647}))
        self.assertFalse(self.c.execute('status')['reachable'])
        self.assertTrue(self.c.execute('start')['reachable'])

    def test_failed_launches_are_bounded_and_reaped(self):
        for mode in ('hang', 'timeout', 'malformed', 'oversized', 'wrong-version', 'wrong-session'):
            with self.subTest(mode=mode):
                c = self.make(FAKE_MODE=mode)
                began = time.monotonic()
                with self.assertRaises(control.ControlError): c.execute('start')
                self.assertLess(time.monotonic() - began, 2.5)
                self.assertIsNotNone(c.last_spawn.poll())
                self.assertFalse(c.record_path.exists())

    def test_existing_handshake_mismatch_is_not_replaced(self):
        reply = self.c.execute('start')
        self.c.version = 'new-version'
        for op in ('start', 'open', 'close'):
            with self.assertRaises(control.ControlError): self.c.execute(op)
        os.kill(reply['pid'], 0)
        # Stop may remove an old version only after OS-level ownership validation.
        self.assertFalse(self.c.execute('stop')['reachable'])

    def test_lock_timeout_is_bounded(self):
        import fcntl
        self.c.execute('start')
        with self.c.lock_path.open('r+') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            with self.assertRaises(control.ControlError): self.c.execute('status')

    def test_symlink_record_is_rejected(self):
        self.c.directory.mkdir(mode=0o700, parents=True)
        target = self.root / 'other'; target.write_text('{}')
        self.c.record_path.symlink_to(target)
        with self.assertRaises(control.ControlError): self.c.execute('start')
        self.assertEqual('{}', target.read_text())

    def test_operation_is_allowlisted(self):
        with self.assertRaises(control.ControlError): self.c.execute('anything; bad')


if __name__ == '__main__':
    unittest.main()
