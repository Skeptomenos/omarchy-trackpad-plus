#!/usr/bin/env python3
"""Per-device settings and native pointer curves for Trackpad Plus."""
import copy
import ctypes
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

STATE_ROOT = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state')
DIRECTORY = STATE_ROOT / 'omarchy/local-touchpads'
STATE = DIRECTORY / 'settings.json'
GENERATED = STATE_ROOT / 'omarchy/toggles/hypr/zz-local-touchpads.lua'
BOOLS = {'enabled', 'natural_scroll', 'tap_to_click', 'disable_while_typing', 'clickfinger_behavior'}
RANGES = {'sensitivity': (-1, 1), 'scroll_factor': (0.01, 2)}
DEFAULT_CURVE = {'precision': 0.3, 'start': 0.8, 'end': 2.8, 'fast': 1.6}
CURVE_RANGES = {'precision': (0.02, 1.5), 'start': (0, 3.8), 'end': (0.2, 4), 'fast': (0.02, 3.5)}


def validate_curve(value):
    if not isinstance(value, dict) or set(value) != set(CURVE_RANGES):
        raise ValueError('Expected precision, start, end, and fast curve controls')
    for key, (low, high) in CURVE_RANGES.items():
        n = value[key]
        if type(n) not in (int, float) or not math.isfinite(n) or not low <= n <= high:
            raise ValueError('Curve control is outside its allowed range')
    if value['end'] - value['start'] < 0.2 - 1e-9:
        raise ValueError('Acceleration end must be at least 0.2 above its start')
    if value['fast'] < value['precision']:
        raise ValueError('Fast movement must not be slower than precision movement')
    return value


def curve_profile(curve):
    """Sample output velocity, not gain; libinput linearly interpolates these points.

    Two samples beyond the visible end (4.0) keep extrapolation at constant gain.
    Keep this function in sync with Curve.js; the cross-language test compares both.
    """
    validate_curve(curve)
    points = []
    for index in range(43):
        x = index * 0.1
        t = max(0, min(1, (x - curve['start']) / (curve['end'] - curve['start'])))
        gain = curve['precision'] + (curve['fast'] - curve['precision']) * t * t * (3 - 2 * t)
        points.append(f'{x * gain:.6f}')
    return 'custom 0.1 ' + ' '.join(points)


def hypr(*args):
    result = subprocess.run(['hyprctl', *args], text=True, capture_output=True, timeout=4, check=True)
    if args[0] == 'eval' and result.stdout.strip() != 'ok':
        raise RuntimeError(result.stdout.strip() or result.stderr.strip() or 'Hyprland rejected settings')
    return result.stdout


def validate_native_profile(profile):
    """Check libinput itself: Hyprland 0.56 ignores set_points' error status.

    This creates a configuration object only; it does not open input devices or
    require elevated permissions. In particular, libinput rejects >64 points.
    """
    lib = ctypes.CDLL('libinput.so.10')
    lib.libinput_config_accel_create.argtypes = [ctypes.c_int]
    lib.libinput_config_accel_create.restype = ctypes.c_void_p
    lib.libinput_config_accel_set_points.argtypes = [ctypes.c_void_p, ctypes.c_int,
        ctypes.c_double, ctypes.c_size_t, ctypes.POINTER(ctypes.c_double)]
    lib.libinput_config_accel_set_points.restype = ctypes.c_int
    lib.libinput_config_accel_destroy.argtypes = [ctypes.c_void_p]
    lib.libinput_config_accel_destroy.restype = None
    config = lib.libinput_config_accel_create(4)  # LIBINPUT_CONFIG_ACCEL_PROFILE_CUSTOM
    if not config:
        raise RuntimeError('libinput could not create a custom acceleration profile')
    try:
        fields = profile.split()
        step = float(fields[1])
        values = list(map(float, fields[2:]))
        for motion_type, spacing, points in [(1, step, values), (2, 1.0, [0.0, 1.0])]:
            native_points = (ctypes.c_double * len(points))(*points)
            status = lib.libinput_config_accel_set_points(config, motion_type, spacing, len(points), native_points)
            if status != 0:
                raise ValueError(f'libinput rejected the acceleration curve (status {status}, {len(points)} points)')
    finally:
        lib.libinput_config_accel_destroy(config)


def validate_native_curve(curve):
    validate_native_profile(curve_profile(curve))


def validate_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.:+-]{1,128}', name):
        raise ValueError('Unsupported trackpad device name')
    return name


def validate_setting(key, value):
    if key == 'accel_profile':
        if value not in ('adaptive', 'flat', 'custom'):
            raise ValueError('Expected adaptive, flat, or custom acceleration')
    elif key == 'curve':
        validate_curve(value)
    elif key == 'curve_preset':
        if value not in ('mac', 'custom'):
            raise ValueError('Unknown curve preset')
    elif key in BOOLS:
        if type(value) is not bool:
            raise ValueError('Expected a boolean')
    elif key in RANGES:
        low, high = RANGES[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Setting is outside its allowed range')
    else:
        raise ValueError('Unknown setting')
    return value


def group_devices(mice):
    groups = {}
    for mouse in mice:
        name = mouse['name']
        is_builtin_apple = name == 'apple-mtp-multi-touch'
        if not is_builtin_apple and not re.search('touchpad|trackpad', name, re.I):
            continue
        validate_name(name)
        if is_builtin_apple or name.startswith('apple-inc.-magic-trackpad'):
            key, label = 'apple', 'Apple'
        elif name == 'ven_06cb:00-06cb:d01d-touchpad':
            key, label = 'dell', 'Dell'
        else:
            key, label = name, name
        groups.setdefault(key, {'id': key, 'label': label, 'names': []})['names'].append(name)
    return groups


def lua_for(groups):
    # hyprctl interprets an argument starting with '--' as a CLI flag.
    lines = ['do -- Managed by davefano.trackpad-plus. Change settings in Trackpad Plus.']
    for group in groups.values():
        fields = []
        for key, value in sorted(group['settings'].items()):
            validate_setting(key, value)
            if key in ('curve', 'curve_preset'):
                continue  # Editor metadata is never emitted as a Hyprland option.
            if key == 'accel_profile' and value == 'custom':
                value = curve_profile(group['settings'].get('curve', DEFAULT_CURVE))
            fields.append(f'{key} = {json.dumps(value)}')
        if group['settings'].get('accel_profile') == 'custom':
            # Explicit identity scrolling, independent of the pointer curve.
            fields.append('scroll_points = "1 0 1"')
        for name in group['names']:
            validate_name(name)
            lines.append('hl.device({ name = ' + json.dumps(name) + ', ' + ', '.join(fields) + ' })')
    return '\n'.join(lines + ['end']) + '\n'


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Refusing to replace a symbolic link')
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save(state):
    for group in state['devices'].values():
        if group['settings'].get('accel_profile') == 'custom':
            validate_native_curve(group['settings'].get('curve', DEFAULT_CURVE))
    atomic_write(GENERATED, lua_for(state['devices']))
    atomic_write(STATE, json.dumps(state, indent=2) + '\n')


def reconcile_generated(state):
    """Recover a removed rule file or an interrupted two-file save from JSON."""
    expected = lua_for(state['devices'])
    if GENERATED.is_file() and GENERATED.read_text() == expected:
        return
    for group in state['devices'].values():
        if group['settings'].get('accel_profile') == 'custom':
            validate_native_curve(group['settings'].get('curve', DEFAULT_CURVE))
    hypr('eval', expected)
    atomic_write(GENERATED, expected)


def defaults():
    values = {}
    for key in sorted(BOOLS - {'enabled'} | {'scroll_factor'}):
        option = json.loads(hypr('getoption', 'input:touchpad:' + key, '-j'))
        values[key] = option.get('bool', option.get('float'))
        validate_setting(key, values[key])
    values['sensitivity'] = json.loads(hypr('getoption', 'input:sensitivity', '-j'))['float']
    values['enabled'] = True
    values['accel_profile'] = 'adaptive'
    return values


def initialize(live):
    base = defaults()
    devices = copy.deepcopy(live)
    # Import the old panel's Dell-only pointer setting without executing its Lua.
    legacy = STATE_ROOT / 'omarchy/toggles/hypr/touchpad-settings.lua'
    text = legacy.read_text() if legacy.is_file() else ''
    overrides = dict(re.findall(r'hl\.device\(\{ name = "([A-Za-z0-9_.:+-]+)", sensitivity = (-?[0-9.]+) \}\)', text))
    for group in devices.values():
        group['settings'] = dict(base)
        for name in group['names']:
            if name in overrides:
                group['settings']['sensitivity'] = validate_setting('sensitivity', float(overrides[name]))
    return {'version': 1, 'devices': devices}


def snapshot(state, live):
    rows = []
    for key in sorted(state['devices'], key=lambda k: (k != 'apple', k != 'dell', k)):
        group = copy.deepcopy(state['devices'][key])
        group['connected'] = key in live
        rows.append(group)
    return {'devices': rows}


def migrate(state):
    """The previous panel inherited the driver's default adaptive profile."""
    updated = copy.deepcopy(state)
    for group in updated['devices'].values():
        settings = group['settings']
        settings.setdefault('accel_profile', 'adaptive')
        curve = settings.get('curve')
        if isinstance(curve, dict) and set(curve) == {'precision', 'transition', 'fast'}:
            transition = curve['transition']
            if type(transition) not in (int, float) or not math.isfinite(transition) or not 0.2 <= transition <= 1.8:
                raise ValueError('Invalid legacy curve transition')
            settings['curve'] = validate_curve({'precision': curve['precision'], 'start': 0,
                                                'end': 2 * transition, 'fast': curve['fast']})
            # The old Mac preset has a different shape from the new starting preset.
            settings['curve_preset'] = 'custom'
        previous = group.get('previous_pointer_feel')
        if previous and 'transition' in previous.get('curve', {}):
            old = previous['curve']
            previous['curve'] = validate_curve({'precision': old['precision'], 'start': 0,
                                               'end': 2 * old['transition'], 'fast': old['fast']})
            if previous['profile'] == 'mac':
                previous['profile'] = 'custom'
    updated['version'] = 3
    return updated


def change(state, key, option, value):
    if key not in state['devices']:
        raise ValueError('Unknown trackpad')
    updated = copy.deepcopy(state)
    settings = updated['devices'][key]['settings']
    if option == 'pointer_feel':
        if not isinstance(value, dict) or set(value) != {'profile', 'curve'}:
            raise ValueError('Expected a pointer profile and curve')
        profile = value['profile']
        if profile not in ('adaptive', 'flat', 'mac', 'custom'):
            raise ValueError('Unknown pointer profile')
        curve = validate_curve(value['curve'])
        old_profile = settings.get('accel_profile', 'adaptive')
        updated['devices'][key]['previous_pointer_feel'] = {
            'profile': settings.get('curve_preset', 'custom') if old_profile == 'custom' else old_profile,
            'curve': copy.deepcopy(settings.get('curve', DEFAULT_CURVE)),
        }
        settings['accel_profile'] = 'custom' if profile in ('mac', 'custom') else profile
        settings['curve'] = dict(DEFAULT_CURVE if profile == 'mac' else curve)
        settings['curve_preset'] = 'mac' if profile == 'mac' else 'custom'
    else:
        validate_setting(option, value)
        settings[option] = value
    if settings.get('accel_profile') == 'custom':
        validate_native_curve(settings.get('curve', DEFAULT_CURVE))
    # Only the selected trackpad receives a live update.
    hypr('eval', lua_for({key: updated['devices'][key]}))
    try:
        save(updated)
    except Exception:
        hypr('eval', lua_for({key: state['devices'][key]}))
        save(state)
        raise
    return updated


def main():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(DIRECTORY / 'settings.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        live = group_devices(json.loads(hypr('devices', '-j'))['mice'])
        command = sys.argv[1] if len(sys.argv) > 1 else 'state'
        if STATE.exists():
            state = json.loads(STATE.read_text())
        elif command in ('state', 'init'):
            state = initialize(live)
            save(state)
        else:
            raise ValueError('Trackpads have not been initialized')
        upgraded = migrate(state)
        if upgraded != state:
            save(upgraded)
            state = upgraded
        # Keep saved settings while discovering trackpads attached after first run.
        previous = copy.deepcopy(state)
        new_devices = {key: group for key, group in live.items() if key not in state['devices']}
        if new_devices:
            state['devices'].update(initialize(new_devices)['devices'])
            state = migrate(state)
        for key, group in live.items():
            if key in state['devices']:
                state['devices'][key]['names'] = sorted(set(state['devices'][key]['names'] + group['names']))
        if state != previous:
            save(state)
        if command == 'set':
            if len(sys.argv) != 5:
                raise ValueError('Usage: trackpads.py set DEVICE OPTION JSON_VALUE')
            state = change(state, sys.argv[2], sys.argv[3], json.loads(sys.argv[4]))
        elif command not in ('state', 'init'):
            raise ValueError('Unknown command')
        reconcile_generated(state)
        print(json.dumps(snapshot(state, live)))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
