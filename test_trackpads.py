import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('trackpads',Path(__file__).with_name('trackpads.py'))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TrackpadTests(unittest.TestCase):
    def setUp(self):
        self.groups=m.group_devices([{'name':n} for n in ['ven_06cb:00-06cb:d01d-touchpad','apple-inc.-magic-trackpad','apple-inc.-magic-trackpad-1','usb-mouse']])
        for g in self.groups.values():
            g['settings']={'enabled':True,'sensitivity':0.3 if g['id']=='dell' else 0.1,'scroll_factor':0.2,'natural_scroll':False,'tap_to_click':True,'clickfinger_behavior':True,'disable_while_typing':True}
        self.state={'version':1,'devices':self.groups}

    def test_groups_two_apple_interfaces_without_mouse(self):
        self.assertEqual(set(self.groups),{'apple','dell'})
        self.assertEqual(len(self.groups['apple']['names']),2)

    def test_acceleration_migration_preserves_existing_settings(self):
        migrated = m.migrate(self.state)
        self.assertEqual(migrated['version'], 3)
        for key in self.groups:
            settings = dict(migrated['devices'][key]['settings'])
            self.assertEqual(settings.pop('accel_profile'), 'adaptive')
            self.assertEqual(settings, self.groups[key]['settings'])
        migrated['devices']['apple']['settings']['accel_profile'] = 'flat'
        self.assertEqual(m.migrate(migrated), migrated)

    def test_acceleration_change_targets_only_selected_trackpad(self):
        state = m.migrate(self.state)
        with patch.object(m, 'hypr') as run, patch.object(m, 'save'):
            updated = m.change(state, 'apple', 'accel_profile', 'flat')
        self.assertEqual(updated['devices']['dell'], state['devices']['dell'])
        self.assertEqual(run.call_args.args[1].count('accel_profile = "flat"'), 2)
        self.assertNotIn('ven_06cb', run.call_args.args[1])
        for value in [True, None, 0, 'custom 1 0 1', 'bad"lua', []]:
            with self.assertRaises(ValueError):
                m.validate_setting('accel_profile', value)

    def test_change_apple_only_and_persist_both(self):
        with tempfile.TemporaryDirectory() as d, patch.object(m,'STATE',Path(d)/'settings.json'), patch.object(m,'GENERATED',Path(d)/'settings.lua'), patch.object(m,'hypr') as run:
            updated=m.change(self.state,'apple','scroll_factor',0.7)
            self.assertEqual(updated['devices']['dell'],self.state['devices']['dell'])
            self.assertEqual(updated['devices']['apple']['settings']['scroll_factor'],0.7)
            lua=run.call_args.args[1]
            self.assertFalse(lua.lstrip().startswith('-'), 'Lua must not be parsed as a hyprctl flag')
            self.assertNotIn('ven_06cb',lua)
            self.assertEqual(lua.count('hl.device('),2)
            self.assertNotIn('hl.config(',m.GENERATED.read_text())
            self.assertEqual(json.loads(m.STATE.read_text()),updated)

    def test_invalid_settings_and_names_rejected_before_apply(self):
        for key,value in [('sensitivity',9),('scroll_factor',float('nan')),('enabled','false'),('unknown',True)]:
            with patch.object(m,'hypr') as run, self.assertRaises(ValueError):m.change(self.state,'apple',key,value)
            run.assert_not_called()
        with self.assertRaises(ValueError):m.validate_name('bad" }); os.execute("x")')

    def test_disabled_or_unplugged_device_remains_selectable(self):
        state=copy.deepcopy(self.state)
        state['devices']['apple']['settings']['enabled']=False
        view=m.snapshot(state,{'dell':self.groups['dell']})
        apple=next(g for g in view['devices'] if g['id']=='apple')
        self.assertFalse(apple['connected'])
        self.assertFalse(apple['settings']['enabled'])
        self.assertEqual(len(apple['names']),2)

    def test_apply_error_does_not_persist(self):
        with patch.object(m,'hypr',side_effect=RuntimeError('rejected')),patch.object(m,'save') as save:
            with self.assertRaises(RuntimeError):m.change(self.state,'dell','sensitivity',0.9)
            save.assert_not_called()

    def test_save_failure_rolls_back(self):
        with patch.object(m,'hypr') as run,patch.object(m,'save',side_effect=[OSError('disk full'),None]):
            with self.assertRaises(OSError):m.change(self.state,'apple','sensitivity',0.5)
            self.assertIn('sensitivity = 0.1',run.call_args.args[1])
            self.assertNotIn('ven_06cb',run.call_args.args[1])

    def test_builtin_apple_is_discovered_and_existing_id_is_preserved(self):
        groups = m.group_devices([{'name': 'apple-mtp-multi-touch'}, {'name': 'usb-mouse'}])
        self.assertEqual(list(groups), ['apple'])
        self.assertEqual(groups['apple']['names'], ['apple-mtp-multi-touch'])

    def test_curve_apply_is_atomic_and_only_emits_native_settings(self):
        state = m.migrate(self.state)
        with patch.object(m, 'hypr') as run, patch.object(m, 'save'):
            updated = m.change(state, 'apple', 'pointer_feel', {'profile': 'mac', 'curve': m.DEFAULT_CURVE})
        self.assertEqual(updated['devices']['dell'], state['devices']['dell'])
        settings = updated['devices']['apple']['settings']
        self.assertEqual(settings['accel_profile'], 'custom')
        self.assertEqual(settings['sensitivity'], 0.1)
        lua = run.call_args.args[1]
        self.assertIn('accel_profile = "custom 0.1 0.000000', lua)
        self.assertIn('scroll_points = "1 0 1"', lua)
        self.assertNotIn('curve =', lua)
        self.assertNotIn('curve_preset', lua)
        with patch.object(m, 'hypr') as run, patch.object(m, 'save', side_effect=[OSError('disk full'), None]):
            with self.assertRaises(OSError):
                m.change(updated, 'apple', 'pointer_feel', {'profile': 'flat', 'curve': m.DEFAULT_CURVE})
        self.assertIn('accel_profile = "custom 0.1', run.call_args.args[1])

    def test_invalid_curve_is_rejected_without_touching_compositor(self):
        for curve in [None, {}, dict(m.DEFAULT_CURVE, precision=True),
                      dict(m.DEFAULT_CURVE, fast=float('inf')),
                      dict(m.DEFAULT_CURVE, fast=0.2),
                      dict(m.DEFAULT_CURVE, start=2.7),
                      dict(m.DEFAULT_CURVE, end=0.5),
                      dict(m.DEFAULT_CURVE, start=float("nan")),
                      dict(m.DEFAULT_CURVE, extra=1)]:
            with patch.object(m, 'hypr') as run, self.assertRaises(ValueError):
                m.change(self.state, 'apple', 'pointer_feel', {'profile': 'custom', 'curve': curve})
            run.assert_not_called()

    def test_precision_range_stays_flat_and_ramp_end_is_independent(self):
        curve = dict(m.DEFAULT_CURVE)
        points = list(map(float, m.curve_profile(curve).split()[2:]))
        for index in range(1, 9):
            self.assertAlmostEqual(points[index] / (index * 0.1), curve['precision'])
        self.assertGreater(points[16] / 1.6, curve['precision'])
        self.assertAlmostEqual(points[28] / 2.8, curve['fast'])
        later_end = list(map(float, m.curve_profile(dict(curve, end=3.6)).split()[2:]))
        self.assertEqual(later_end[:9], points[:9])
        self.assertLess(later_end[20], points[20])

    def test_legacy_curve_migration_preserves_response(self):
        state = m.migrate(self.state)
        state['devices']['apple']['settings'].update(accel_profile='custom', curve_preset='mac',
            curve={'precision': 0.4, 'transition': 0.9, 'fast': 1.6})
        updated = m.migrate(state)
        settings = updated['devices']['apple']['settings']
        self.assertEqual(settings['curve'], {'precision': 0.4, 'start': 0, 'end': 1.8, 'fast': 1.6})
        self.assertEqual(settings['curve_preset'], 'custom')
        values = list(map(float, m.curve_profile(settings['curve']).split()[2:]))
        for index, value in enumerate(values):
            speed = index * 0.1
            t = min(1, speed / 1.8)
            self.assertAlmostEqual(value, speed * (0.4 + 1.2 * t * t * (3 - 2 * t)), places=5)
        self.assertEqual(m.migrate(updated), updated)

    def test_graph_matches_backend_and_has_constant_gain_tail(self):
        curves = [m.DEFAULT_CURVE, {'precision': 0.08, 'start': 2.0, 'end': 3.6, 'fast': 0.65}, {'precision': 0.2, 'start': 0, 'end': 0.4, 'fast': 3.5},
                  {'precision': 1.5, 'start': 3.4, 'end': 3.6, 'fast': 1.5}]
        script = "const c=require('./Curve.js'); console.log(JSON.stringify(JSON.parse(process.argv[1]).map(x=>c.points(x))))"
        plotted = json.loads(subprocess.check_output(['node', '-e', script, json.dumps(curves)], cwd=Path(__file__).parent))
        for curve, graph in zip(curves, plotted):
            points = list(map(float, m.curve_profile(curve).split()[2:]))
            self.assertEqual(graph, points)
            self.assertEqual(points[0], 0)
            self.assertEqual(points, sorted(points))
            self.assertAlmostEqual((points[-1] - points[-2]) / 0.1, curve['fast'])

    def test_native_libinput_accepts_curve_and_rejects_old_81_point_payload(self):
        m.validate_native_curve(m.DEFAULT_CURVE)
        slow = dict(m.DEFAULT_CURVE, precision=0.02, fast=0.02)
        m.validate_native_curve(slow)
        old_payload = 'custom 0.05 ' + ' '.join(str(i * 0.001) for i in range(81))
        with self.assertRaisesRegex(ValueError, 'libinput rejected.*81 points'):
            m.validate_native_profile(old_payload)

    def test_native_rejection_never_applies_or_saves_settings(self):
        with patch.object(m, 'validate_native_curve', side_effect=ValueError('libinput rejected curve')):
            with patch.object(m, 'hypr') as run, patch.object(m, 'save') as save:
                with self.assertRaisesRegex(ValueError, 'libinput rejected'):
                    m.change(self.state, 'apple', 'pointer_feel', {'profile': 'custom', 'curve': m.DEFAULT_CURVE})
                run.assert_not_called()
                save.assert_not_called()

    def test_legacy_undo_curve_is_migrated_and_restorable(self):
        state = m.migrate(self.state)
        state['devices']['apple']['previous_pointer_feel'] = {
            'profile': 'mac', 'curve': {'precision': 0.3, 'transition': 0.9, 'fast': 1.6}}
        updated = m.migrate(state)
        previous = updated['devices']['apple']['previous_pointer_feel']
        self.assertEqual(previous['profile'], 'custom')
        self.assertEqual(previous['curve']['end'], 1.8)
        with patch.object(m, 'hypr'), patch.object(m, 'save'):
            restored = m.change(updated, 'apple', 'pointer_feel', previous)
        self.assertEqual(restored['devices']['apple']['settings']['curve'], previous['curve'])
        self.assertEqual(m.migrate(updated), updated)

    def test_save_validates_custom_profile_before_writing_either_file(self):
        state = m.migrate(self.state)
        state['devices']['apple']['settings']['accel_profile'] = 'custom'
        with patch.object(m, 'validate_native_curve', side_effect=ValueError('unsupported libinput')):
            with patch.object(m, 'atomic_write') as write, self.assertRaises(ValueError):
                m.save(state)
            write.assert_not_called()

if __name__=='__main__':unittest.main()
