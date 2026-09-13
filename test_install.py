"""Exercise a tracked-only installation against a fake compositor in temporary state."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plugin = self.root / 'plugin'
        self.plugin.mkdir()
        repo = Path(__file__).resolve().parent
        tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=repo).decode().split('\0')
        for name in filter(None, tracked):
            source = repo / name
            if source.is_file():
                destination = self.plugin / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        self.assertTrue((self.plugin / 'trackpads.py').is_file(), 'Backend must be tracked')
        self.env = dict(os.environ, XDG_STATE_HOME=str(self.root / 'state'),
                        PATH=str(self.root) + os.pathsep + os.environ['PATH'],
                        TRACKPAD_TEST_ROOT=str(self.root))
        self.devices = self.root / 'devices.json'
        self.devices.write_text(json.dumps({'mice': [
            {'name': 'ven_06cb:00-06cb:d01d-touchpad'},
            {'name': 'apple-inc.-magic-trackpad'},
            {'name': 'apple-inc.-magic-trackpad-1'}]}))
        fake = self.root / 'hyprctl'
        fake.write_text('#!' + sys.executable + '''
import json, os, sys
from pathlib import Path
root = Path(os.environ['TRACKPAD_TEST_ROOT'])
if sys.argv[1] == 'devices':
    print((root / 'devices.json').read_text())
elif sys.argv[1] == 'getoption':
    option = sys.argv[2].split(':')[-1]
    print(json.dumps({'float': 0.2} if option in ('sensitivity', 'scroll_factor')
                     else {'bool': option != 'natural_scroll'}))
elif sys.argv[1] == 'eval':
    with (root / 'eval.log').open('a') as stream:
        stream.write(sys.argv[2])
    print('ok')
else:
    raise SystemExit(2)
''')
        fake.chmod(0o700)

    def call(self, *args):
        result = subprocess.run([sys.executable, str(self.plugin / 'trackpads.py'), *args],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_fresh_install_initializes_and_persists_independent_settings(self):
        before = self.call('state')  # The same first command used by Panel.qml.
        self.assertEqual({d['id'] for d in before['devices']}, {'apple', 'dell'})
        after = self.call('set', 'apple', 'accel_profile', '"flat"')
        self.assertEqual(next(d for d in before['devices'] if d['id'] == 'dell'),
                         next(d for d in after['devices'] if d['id'] == 'dell'))
        self.assertEqual(self.call('state'), after)
        lua = (self.root / 'eval.log').read_text()
        self.assertEqual(lua.count('accel_profile = "flat"'), 2)
        self.assertNotIn('ven_06cb', lua)
        generated = self.root / 'state/omarchy/toggles/hypr/zz-local-touchpads.lua'
        self.assertIn('accel_profile = "flat"', generated.read_text())

    def test_device_attached_after_empty_first_run_is_discovered(self):
        self.devices.write_text('{"mice": []}')
        self.assertEqual(self.call('state')['devices'], [])
        self.devices.write_text('{"mice": [{"name": "apple-inc.-magic-trackpad"}]}')
        self.assertEqual(self.call('state')['devices'][0]['id'], 'apple')
        self.call('set', 'apple', 'sensitivity', '0.4')
        self.assertEqual(self.call('state')['devices'][0]['settings']['sensitivity'], 0.4)

    def test_lock_stall_is_bounded_and_next_read_recovers(self):
        self.call('state')
        lock_path = self.root / 'state/omarchy/local-touchpads/settings.lock'
        with lock_path.open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = subprocess.run(['timeout', '-k', '2', '0.1', sys.executable,
                                     str(self.plugin / 'trackpads.py'), 'state'],
                                    env=self.env, capture_output=True, timeout=4)
            self.assertEqual(result.returncode, 124)
        self.assertEqual(len(self.call('state')['devices']), 2)

    def test_builtin_apple_curve_survives_restart_and_can_return_to_adaptive(self):
        self.devices.write_text('{"mice": [{"name": "apple-mtp-multi-touch"}]}')
        before = self.call('state')['devices'][0]
        self.assertTrue(before['connected'])
        self.assertTrue((self.plugin / 'CurveEditor.qml').is_file())
        self.assertTrue((self.plugin / 'Curve.js').is_file())
        value = {'profile': 'custom', 'curve': {'precision': 0.3, 'start': 0.8, 'end': 2.4, 'fast': 2.0}}
        self.call('set', 'apple', 'pointer_feel', json.dumps(value))
        after = self.call('state')['devices'][0]
        self.assertEqual(after['settings']['curve'], value['curve'])
        self.assertEqual(after['settings']['accel_profile'], 'custom')
        self.assertEqual(after['previous_pointer_feel']['profile'], 'adaptive')
        self.assertEqual(after['settings']['scroll_factor'], before['settings']['scroll_factor'])
        value['profile'] = 'adaptive'
        self.call('set', 'apple', 'pointer_feel', json.dumps(value))
        self.assertEqual(self.call('state')['devices'][0]['settings']['accel_profile'], 'adaptive')

    def test_new_identity_preserves_legacy_state_and_repairs_missing_rules(self):
        manifest = json.loads((self.plugin / 'manifest.json').read_text())
        self.assertEqual(manifest['id'], 'davefano.trackpad-plus')
        self.assertEqual(manifest['name'], 'Trackpad Plus')
        self.call('state')
        self.call('set', 'apple', 'sensitivity', '-0.4')
        state_path = self.root / 'state/omarchy/local-touchpads/settings.json'
        saved = state_path.read_bytes()
        generated = self.root / 'state/omarchy/toggles/hypr/zz-local-touchpads.lua'
        for damage in ('missing', 'interrupted-save'):
            if damage == 'missing':
                generated.unlink()
            else:
                generated.write_text('do -- incomplete previous write\nend\n')
            self.call('state')
            self.assertEqual(state_path.read_bytes(), saved)
            self.assertIn('sensitivity = -0.4', generated.read_text())
            self.assertIn('davefano.trackpad-plus', generated.read_text())

    def test_slow_scrolling_persists_without_changing_pointer_curve(self):
        self.call('state')
        value = {'profile': 'custom', 'curve': {'precision': 0.05, 'start': 0.8, 'end': 2.8, 'fast': 0.85}}
        before = self.call('set', 'apple', 'pointer_feel', json.dumps(value))
        original = next(d for d in before['devices'] if d['id'] == 'apple')
        for factor in [0.05, 0.01]:
            after = self.call('set', 'apple', 'scroll_factor', str(factor))
            self.assertEqual(after, self.call('state'))
            apple = next(d for d in after['devices'] if d['id'] == 'apple')
            expected = dict(original['settings'], scroll_factor=factor)
            self.assertEqual(apple['settings'], expected)
            self.assertEqual(apple['previous_pointer_feel'], original['previous_pointer_feel'])
            self.assertEqual(next(d for d in after['devices'] if d['id'] == 'dell'),
                             next(d for d in before['devices'] if d['id'] == 'dell'))


if __name__ == '__main__':
    unittest.main()
