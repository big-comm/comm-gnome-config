"""Resource compatibility and version selection checks."""

import importlib.util
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
THEMES = ROOT / "usr/share/gnome-shell"
SELECTOR = ROOT / "usr/share/libalpm/scripts/gdm-theme-path"
PREFIX = "/org/gnome/shell/theme/"
spec = importlib.util.spec_from_file_location("builder", ROOT / "tools/build-gdm-theme.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def extract(bundle, name):
    return subprocess.check_output(["gresource", "extract", str(bundle), PREFIX + name])


class ThemeTests(unittest.TestCase):
    def test_monitor_uses_matching_default(self):
        path = ROOT / 'usr/bin/wallpaper-monitor'
        loader = SourceFileLoader('wallpaper_monitor', str(path))
        module_spec = importlib.util.spec_from_loader(loader.name, loader)
        monitor = importlib.util.module_from_spec(module_spec)
        with mock.patch('logging.basicConfig'):
            loader.exec_module(monitor)
        for default, exists, expected in (
            ('/themes/51.default', True, True),
            ('/themes/51.default', False, False),
            (None, False, False),
        ):
            with self.subTest(default=default, exists=exists):
                with mock.patch.object(monitor, 'is_gdm_settings_installed', return_value=False), \
                     mock.patch.object(monitor, 'run_command', return_value=default) as command, \
                     mock.patch.object(monitor.os.path, 'exists', return_value=exists):
                    self.assertEqual(monitor.should_monitor_wallpaper(force=True), expected)
                    command.assert_called_once_with(['/usr/share/libalpm/scripts/gdm-theme-path', 'default'])

    def test_package_install_selects_custom_and_compatibility_theme(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            selector = directory / 'selector'
            selector.write_text(f'#!/bin/sh\nprintf "{directory}/%s\\n" "$1"\n')
            selector.chmod(0o755)
            for kind in ('big', 'default'):
                (directory / kind).touch()
            installer = directory / 'install.sh'
            installer.write_text((ROOT / 'pkgbuild/pkgbuild.install').read_text().replace(
                '/usr/share/libalpm/scripts/gdm-theme-path', str(selector)))
            for installed, kind, code in (('true', 'default', 1), ('false', 'big', 0)):
                with self.subTest(gdm_settings=installed):
                    script = '''source "$1"
printMsg() { :; }
is_gdm_settings_installed() { "$2"; }
install_gresource() { printf '%s\\n' "$1"; }
'''.replace('is_gdm_settings_installed() { "$2"; }',
            f'is_gdm_settings_installed() {{ {installed}; }}') + 'apply_appropriate_theme\n'
                    result = subprocess.run(['bash', '-c', script, 'test', str(installer)],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, code)
                    self.assertEqual(result.stdout.strip(), str(directory / kind))

    def test_version_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            shell = Path(directory) / "gnome-shell"
            for version, base in (("49.5", "gnome-shell-theme"),
                                  ("50.4", "gnome-shell-theme"),
                                  ("51.rc", "gnome-shell-theme-51"),
                                  ("51.0", "gnome-shell-theme-51")):
                shell.write_text(f"#!/bin/sh\nprintf 'GNOME Shell {version}\\n'\n")
                shell.chmod(0o755)
                for kind in ("big", "default"):
                    with self.subTest(version=version, kind=kind):
                        result = subprocess.check_output(
                            [str(SELECTOR), kind], text=True,
                            env={**os.environ, "PATH": directory + ":" + os.environ["PATH"]},
                        )
                        self.assertEqual(result.strip(), f"/usr/share/gnome-shell/{base}.gresource.{kind}")
            shell.write_text("#!/bin/sh\necho 'GNOME Shell 52.0'\n")
            result = subprocess.run([str(SELECTOR)], capture_output=True,
                                    env={**os.environ, "PATH": directory + ":" + os.environ["PATH"]})
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")

    def test_native_styles_and_assets_preserved(self):
        original = THEMES / "gnome-shell-theme-51.gresource.default"
        custom = THEMES / "gnome-shell-theme-51.gresource.big"
        names = subprocess.check_output(["gresource", "list", str(original)], text=True).splitlines()
        overlay = (ROOT / "themes/gdm-51.css").read_bytes()
        for resource in names:
            name = resource.removeprefix(PREFIX)
            with self.subTest(resource=name):
                expected = extract(original, name)
                if name in ("gnome-shell-dark.css", "gnome-shell-light.css"):
                    expected += b"\n" + overlay
                self.assertEqual(extract(custom, name), expected)

    def test_reproducible_build_and_reject_custom_input(self):
        original = THEMES / "gnome-shell-theme-51.gresource.default"
        custom = THEMES / "gnome-shell-theme-51.gresource.big"
        with tempfile.TemporaryDirectory() as directory:
            wallpaper = Path(directory) / "fundo.jpg"
            wallpaper.write_bytes(extract(custom, "fundo.jpg"))
            result = Path(directory) / "rebuilt.gresource"
            builder.build(original, wallpaper, result)
            self.assertEqual(result.read_bytes(), custom.read_bytes())
            with self.assertRaisesRegex(ValueError, "pristine"):
                builder.build(custom, wallpaper, result)


if __name__ == "__main__":
    unittest.main()
