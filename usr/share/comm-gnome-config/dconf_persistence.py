#!/usr/bin/python
"""Durable GNOME snapshots. Call Store methods under the shared writer lock."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

PROTOCOL = 1


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate(text):
    from gi.repository import GLib
    if not text.strip():
        raise ValueError('Empty dconf snapshot')
    keyfile = GLib.KeyFile()
    keyfile.load_from_data(text, len(text.encode()), GLib.KeyFileFlags.NONE)
    values = {}
    for group in keyfile.get_groups()[0]:
        if group.startswith('/') or group.endswith('/') or '//' in group:
            raise ValueError('Invalid dconf group')
        for key in keyfile.get_keys(group)[0]:
            if '/' in key or not key:
                raise ValueError('Invalid dconf key')
            value = keyfile.get_value(group, key)
            GLib.Variant.parse(None, value, None, None)
            values[f'/{group}/{key}'] = value
    if not values:
        raise ValueError('No dconf values')
    return values


def record(text):
    validate(text)
    return {'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}


def checked(item):
    text = item['text']
    if hashlib.sha256(text.encode()).hexdigest() != item['sha256']:
        raise ValueError('Snapshot checksum mismatch')
    validate(text)
    return text


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.state_path = self.path.with_name(self.path.name + '.state.json')
        self.marker = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'dconf-sync-gnome.lock'

    @contextmanager
    def lock(self, blocking=False):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (self.path.parent / 'big-gnome-center-layout.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            yield

    def read(self):
        try:
            state = json.loads(self.state_path.read_text())
        except FileNotFoundError:
            return {'version': PROTOCOL, 'generations': [], 'transaction': None}
        if state.get('version') != PROTOCOL or not isinstance(state.get('generations'), list):
            raise ValueError('Unsupported persistence state')
        return state

    def write(self, state):
        atomic_write(self.state_path, json.dumps(state, ensure_ascii=False) + '\n')

    def candidates(self, state):
        if state['generations']:
            # The journal is authoritative once migrated; exported text may be torn.
            for item in state['generations']:
                try:
                    yield checked(item)
                except Exception:
                    continue
            return
        for path in (self.path, self.path.with_name(self.path.name + '.bak')):
            try:
                text = path.read_text()
                validate(text)
                yield text
            except Exception:
                continue

    def publish(self, text, managed=False, staged=False):
        item = record(text)
        state = self.read()
        history = []
        if not state['generations']:
            candidate = next(self.candidates(state), None)
            if candidate is not None:
                state['generations'] = [record(candidate)]
        for old in state['generations']:
            try:
                checked(old)
            except Exception:
                continue
            if old != item and old not in history:
                history.append(old)
        self.export(text, history[:2])
        if managed:
            atomic_write(self.path.with_name(self.path.name + '.big-gnome-center.sha256'),
                         item['sha256'] + '  ' + self.path.name + '\n')
        # A crash before this commit keeps the preceding generation authoritative.
        self.write({'version': PROTOCOL, 'generations': [item, *history[:2]],
                    'transaction': None, 'managed': managed, 'staged': staged})

    def export(self, text, history=()):
        for index, old in enumerate(history):
            atomic_write(self.path.with_name(self.path.name + ('.bak' if index == 0 else '.bak.2')), checked(old))
        atomic_write(self.path, text)

    def begin(self):
        state = self.read()
        if not state['generations']:
            candidate = next(self.candidates(state), None)
            if candidate is None:
                candidate = dconf('dump', '/')
            state['generations'] = [record(candidate)]
        elif next(self.candidates(state), None) is None:
            raise ValueError('No valid recovery generation')
        state['transaction'] = {'pid': os.getpid(), 'status': 'applying'}
        self.write(state)

    def abort(self):
        state = self.read()
        state['transaction'] = {'pid': os.getpid(), 'status': 'recovery-required'}
        self.write(state)

    def complete_without_snapshot(self):
        state = self.read()
        state['transaction'] = None
        self.write(state)

    def import_snapshot(self, text):
        """Explicitly accept reviewed text for next login, including metadata repair."""
        item = record(text)
        try:
            self.read()
        except (ValueError, KeyError, TypeError):
            damaged = self.state_path.read_text()
            atomic_write(self.state_path.with_name(
                self.state_path.name + f'.rejected-{time.time_ns()}'), damaged)
            self.export(text)
            self.write({'version': PROTOCOL, 'generations': [item], 'transaction': None,
                        'managed': True, 'staged': True})
            return
        self.publish(text, managed=True, staged=True)

    def guarded(self):
        state = self.read()
        if state.get('transaction'):
            candidate = next(self.candidates(state), None)
            if candidate is not None:
                atomic_write(self.path, candidate)
            print('Persistence paused: incomplete layout; reapply a layout or log in again.', file=sys.stderr)
            return True
        if state.get('staged'):
            return True
        if self.marker.exists():
            try:
                os.kill(int(self.marker.read_text().strip()), 0)
                return True
            except ProcessLookupError:
                self.marker.unlink(missing_ok=True)
            except (ValueError, PermissionError):
                return True
        return False

    def managed(self):
        try:
            digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        except FileNotFoundError:
            return False
        for suffix in ('.big-gnome-center.sha256', '.layout-switcher.sha256'):
            try:
                if self.path.with_name(self.path.name + suffix).read_text().split()[0] == digest:
                    return True
            except (FileNotFoundError, IndexError):
                pass
        return False


def dconf(*args, text=None):
    result = subprocess.run(['dconf', *args], input=text, text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr or 'dconf command failed')
    return result.stdout


def save(store, final=False):
    with store.lock():
        if store.guarded():
            return final
        if not final and store.managed() and store.path.exists() and time.time() - store.path.stat().st_mtime < 10:
            return False
        if final and store.managed():
            previous = next(store.candidates(store.read()), None)
            if previous is None:
                return False
            # Preserve shutdown-sensitive keys; merge wallpaper changes only.
            values = validate(previous)
            changed = False
            for key in ('/org/gnome/desktop/background/picture-uri',
                        '/org/gnome/desktop/background/picture-uri-dark',
                        '/org/gnome/desktop/screensaver/picture-uri'):
                live = dconf('read', key).strip()
                if live and live != values.get(key):
                    values[key] = live
                    changed = True
            if changed:
                groups = {}
                for key, value in values.items():
                    group, name = key[1:].rsplit('/', 1)
                    groups.setdefault(group, []).append(f'{name}={value}')
                store.publish('\n\n'.join(f'[{group}]\n' + '\n'.join(lines)
                                             for group, lines in groups.items()) + '\n', managed=True)
            return True
        text = dconf('dump', '/')
        values = validate(text)
        if values.get('/org/gnome/desktop/interface/icon-theme', '') in ('', "'default'", "'HighContrast'"):
            return False
        state = store.read()
        if not state['generations']:
            candidate = next(store.candidates(state), None)
            if candidate is not None:
                state['generations'] = [record(candidate)]
                store.write(state)
        store.publish(text)
        for suffix in ('.big-gnome-center.sha256', '.layout-switcher.sha256'):
            store.path.with_name(store.path.name + suffix).unlink(missing_ok=True)
        return True


def login(store):
    with store.lock(blocking=True):
        state = store.read()
        candidate = next(store.candidates(state), None)
        if candidate is None:
            if state['generations'] or store.path.exists() or store.path.with_name(store.path.name + '.bak').exists():
                raise ValueError('No valid saved configuration; live dconf preserved')
            return
        # Validation occurs before destructive reset. Retain runtime recovery too.
        previous = dconf('dump', '/')
        if previous.strip():
            validate(previous)
        store.begin()
        try:
            dconf('reset', '-f', '/')
            dconf('load', '/', text=candidate)
        except Exception:
            if previous.strip():
                dconf('reset', '-f', '/')
                dconf('load', '/', text=previous)
            store.abort()
            raise
        store.publish(candidate)
        store.marker.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('save', 'stop', 'login', 'import', 'firstboot-light'))
    parser.add_argument('file', nargs='?')
    args = parser.parse_args()
    store = Store(Path.home() / '.config/dconf/settings.gnome')
    try:
        if args.action == 'login':
            login(store)
        elif args.action == 'firstboot-light':
            with store.lock(blocking=True):
                state = store.read()
                candidate = next(store.candidates(state), None)
                if candidate is not None:
                    candidate = candidate.replace("color-scheme='prefer-dark'", "color-scheme='default'")
                    candidate = candidate.replace("gtk-theme='adw-gtk3-dark'", "gtk-theme='adw-gtk3'")
                    store.publish(candidate, managed=True, staged=state.get('staged', False))
        elif args.action == 'import':
            if not args.file:
                parser.error('import requires a reviewed text snapshot')
            with store.lock():
                store.import_snapshot(Path(args.file).read_text())
        elif not save(store, final=args.action == 'stop'):
            return 1
    except BlockingIOError:
        return 0 if args.action == 'stop' else 1
    except Exception as error:
        print(f'dconf persistence: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
