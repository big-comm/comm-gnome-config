"""Persistence failures never promote unconfirmed desktop state."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('persistence', Path(__file__).resolve().parents[1] / 'usr/share/comm-gnome-config/dconf_persistence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
OLD = "[org/gnome/desktop/interface]\nicon-theme='test'\n\n[org/example]\nvalue='old'\n"
NEW = OLD.replace("'old'", "'new'")


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = p.Store(Path(self.directory.name) / 'settings.gnome')
        self.store.marker = Path(self.directory.name) / 'marker'
        self.store.path.write_text(OLD)

    def test_failed_apply_quarantines_live_dump(self):
        self.store.begin()
        self.store.path.write_text(NEW)
        self.store.abort()
        with patch.object(p, 'dconf') as command:
            self.assertFalse(p.save(self.store))
            command.assert_not_called()
        self.assertEqual(self.store.path.read_text(), OLD)

    def test_process_death_does_not_require_pid_marker(self):
        self.store.begin()
        self.store.path.write_text(NEW)
        fresh = p.Store(self.store.path)
        self.assertTrue(fresh.guarded())
        self.assertEqual(fresh.path.read_text(), OLD)

    def test_first_apply_without_snapshot_captures_live_recovery(self):
        self.store.path.unlink()
        with patch.object(p, 'dconf', return_value=OLD):
            self.store.begin()
        self.store.path.write_text(NEW)
        self.assertTrue(self.store.guarded())
        self.assertEqual(self.store.path.read_text(), OLD)

    def test_first_apply_without_snapshot_or_live_values_fails(self):
        self.store.path.unlink()
        with patch.object(p, 'dconf', return_value=''):
            with self.assertRaises(ValueError):
                self.store.begin()
        self.assertFalse(self.store.path.exists())

    def test_theme_marker_invalidation_allows_final_save(self):
        self.store.publish(OLD, managed=True)
        self.store.path.with_name(self.store.path.name + '.big-gnome-center.sha256').unlink()
        with patch.object(p, 'dconf', return_value=NEW):
            self.assertTrue(p.save(self.store, final=True))
        self.assertEqual(self.store.path.read_text(), NEW)

    def test_successful_retry_releases_quarantine(self):
        self.store.begin()
        self.store.abort()
        self.store.begin()
        self.store.publish(NEW, managed=True)
        self.assertFalse(self.store.guarded())
        self.assertEqual(self.store.path.read_text(), NEW)

    def test_staged_next_login_layout_never_saves_old_runtime(self):
        self.store.publish(NEW, managed=True, staged=True)
        with patch.object(p, 'dconf') as command:
            self.assertFalse(p.save(self.store))
            self.assertTrue(p.save(self.store, final=True))
            command.assert_not_called()
        self.assertEqual(self.store.path.read_text(), NEW)

    def test_crash_while_replacing_staged_layout_restores_staged_commit(self):
        self.store.publish(OLD, managed=True, staged=True)
        self.store.begin()
        self.store.path.write_text(NEW)
        self.assertTrue(self.store.guarded())
        self.assertEqual(self.store.path.read_text(), OLD)

    def test_login_releases_staged_and_failed_transactions(self):
        self.store.publish(NEW, managed=True, staged=True)
        with patch.object(p, 'dconf', return_value=OLD):
            p.login(self.store)
        self.assertFalse(self.store.guarded())
        self.assertEqual(self.store.path.read_text(), NEW)

    def test_failed_login_load_restores_live_values_and_retains_journal(self):
        calls = []

        def command(*args, text=None):
            calls.append((args, text))
            if args[0] == 'dump':
                return NEW
            if args[0] == 'load' and text == OLD:
                raise RuntimeError('load failure')
            return ''

        with patch.object(p, 'dconf', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'load failure'):
                p.login(self.store)
        self.assertEqual(calls[-1], (('load', '/'), NEW))
        self.assertIsNotNone(self.store.read()['transaction'])

    def test_failed_login_recovery_keeps_journal(self):
        def command(*args, text=None):
            if args[0] == 'dump':
                return NEW
            if args[0] == 'load':
                raise RuntimeError('database unavailable')
            return ''
        with patch.object(p, 'dconf', side_effect=command):
            with self.assertRaises(RuntimeError):
                p.login(self.store)
        self.assertIsNotNone(self.store.read()['transaction'])

    def test_empty_dump_cannot_replace_existing_generation(self):
        self.store.publish(OLD)
        with patch.object(p, 'dconf', return_value=''):
            with self.assertRaises(ValueError):
                p.save(self.store)
        self.assertEqual(self.store.path.read_text(), OLD)

    def test_atomic_write_failure_preserves_destination_and_cleans_temp(self):
        with patch.object(p.os, 'replace', side_effect=OSError('rename failed')):
            with self.assertRaises(OSError):
                p.atomic_write(self.store.path, NEW)
        self.assertEqual(self.store.path.read_text(), OLD)
        self.assertEqual(list(self.store.path.parent.glob('.*')), [])

    def test_three_independent_checksummed_generations(self):
        for index in range(5):
            self.store.publish(OLD.replace('old', str(index)))
        state = self.store.read()
        self.assertEqual(len(state['generations']), 3)
        state['generations'][0]['text'] = NEW
        self.store.write(state)
        self.assertIn("value='3'", next(self.store.candidates(self.store.read())))

    def test_invalid_legacy_files_do_not_reset_live_database(self):
        self.store.path.write_text('[org/example]\nvalue=invalid variant\n')
        with patch.object(p, 'dconf') as command:
            with self.assertRaisesRegex(ValueError, 'No valid'):
                p.login(self.store)
            command.assert_not_called()

    def test_missing_primary_recovers_legacy_backup(self):
        self.store.path.unlink()
        self.store.path.with_name('settings.gnome.bak').write_text(OLD)
        self.assertEqual(next(self.store.candidates(self.store.read())), OLD)

    def test_valid_syntax_truncation_cannot_replace_committed_generation(self):
        self.store.publish(OLD)
        self.store.path.write_text("[org/gnome/desktop/interface]\nicon-theme='test'\n")
        with patch.object(p, 'dconf', return_value=NEW) as command:
            p.login(self.store)
        self.assertIn(unittest.mock.call('load', '/', text=OLD), command.call_args_list)

    def test_explicit_import_accepts_intentional_minimal_file(self):
        minimal = "[org/example]\nvalue='minimal'\n"
        self.store.import_snapshot(minimal)
        self.assertEqual(next(self.store.candidates(self.store.read())), minimal)
        self.assertTrue(self.store.read()['staged'])

    def test_explicit_import_repairs_damaged_metadata_and_archives_it(self):
        self.store.state_path.write_text('{damaged')
        self.store.import_snapshot(NEW)
        self.assertEqual(next(self.store.candidates(self.store.read())), NEW)
        self.assertTrue(self.store.read()['staged'])
        rejected = list(self.store.path.parent.glob('*.rejected-*'))
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].read_text(), '{damaged')

    def test_export_failure_keeps_old_commit_and_guard(self):
        self.store.begin()
        with patch.object(p, 'atomic_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.publish(NEW)
        self.assertIsNotNone(self.store.read()['transaction'])
        self.assertEqual(next(self.store.candidates(self.store.read())), OLD)

    def test_commit_failure_after_export_recovers_old_generation(self):
        self.store.begin()
        with patch.object(self.store, 'write', side_effect=OSError('commit failed')):
            with self.assertRaises(OSError):
                self.store.publish(NEW)
        self.assertTrue(self.store.guarded())
        self.assertEqual(self.store.path.read_text(), OLD)

    def test_writer_lock_is_shared_and_stable(self):
        other = p.Store(self.store.path)
        with self.store.lock():
            with self.assertRaises(BlockingIOError):
                with other.lock():
                    self.fail('overlap accepted')
        with other.lock():
            self.assertTrue((self.store.path.parent / 'big-gnome-center-layout.lock').exists())

    def test_both_marker_names_protect_final_save(self):
        for suffix in ('.big-gnome-center.sha256', '.layout-switcher.sha256'):
            with self.subTest(suffix=suffix):
                marker = self.store.path.with_name(self.store.path.name + suffix)
                marker.write_text(p.record(OLD)['sha256'])
                with patch.object(p, 'dconf', return_value='') as command:
                    self.assertTrue(p.save(self.store, final=True))
                self.assertTrue(all(call.args[0] == 'read' for call in command.call_args_list))
                marker.unlink()

    def test_wallpaper_final_save_keeps_extension_values(self):
        self.store.publish(OLD, managed=True)
        with patch.object(p, 'dconf', return_value="'file:///wall.jpg'"):
            self.assertTrue(p.save(self.store, final=True))
        self.assertIn("value='old'", self.store.path.read_text())
        self.assertIn("picture-uri='file:///wall.jpg'", self.store.path.read_text())

    def test_corrupt_state_fails_closed(self):
        self.store.state_path.write_text('{broken')
        with patch.object(p, 'dconf') as command:
            with self.assertRaises(json.JSONDecodeError):
                p.save(self.store)
            command.assert_not_called()

    def test_atomic_write_leaves_no_shared_temporary_file(self):
        self.store.publish(OLD)
        self.assertEqual(list(self.store.path.parent.glob('.*')), [])


if __name__ == '__main__':
    unittest.main()
