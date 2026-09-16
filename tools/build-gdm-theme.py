#!/usr/bin/env python3
"""Append the GDM overlay to a pristine GNOME 51 resource bundle."""

import argparse
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import xml.etree.ElementTree as ET

PREFIX = "/org/gnome/shell/theme/"
ROOT = Path(__file__).resolve().parents[1]


def build(original, wallpaper, output):
    resources = subprocess.check_output(
        ["gresource", "list", str(original)], text=True
    ).splitlines()
    overlay = (ROOT / "themes/gdm-51.css").read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        manifest = ET.Element("gresources")
        group = ET.SubElement(manifest, "gresource", prefix=PREFIX.rstrip("/"))
        files = {}
        for resource in resources:
            if not resource.startswith(PREFIX):
                raise ValueError(f"Unexpected resource: {resource}")
            name = resource.removeprefix(PREFIX)
            if ".." in PurePosixPath(name).parts:
                raise ValueError(f"Unsafe resource: {resource}")
            data = subprocess.check_output(["gresource", "extract", str(original), resource])
            if name in ("gnome-shell-dark.css", "gnome-shell-light.css"):
                if b"BigCommunity GDM" in data:
                    raise ValueError("A pristine upstream resource is required")
                if b".login-dialog-input-well" not in data:
                    raise ValueError("The resource is not a GNOME 51 theme")
                data += b"\n" + overlay
            files[name] = data
        # Preserve high contrast and all upstream assets byte-for-byte.
        for required in ("gnome-shell-dark.css", "gnome-shell-light.css", "gnome-shell-high-contrast.css"):
            if required not in files:
                raise ValueError(f"Missing stylesheet: {required}")
        files["fundo.jpg"] = Path(wallpaper).read_bytes()
        for name, data in sorted(files.items()):
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            ET.SubElement(group, "file").text = name
        xml = directory / "theme.gresource.xml"
        ET.ElementTree(manifest).write(xml, encoding="utf-8", xml_declaration=True)
        subprocess.run([
            "glib-compile-resources", str(xml), f"--sourcedir={directory}",
            f"--target={output}",
        ], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("wallpaper", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.original.resolve(), args.wallpaper.resolve(), args.output.resolve())
