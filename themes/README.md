# GDM themes

GNOME 49/50 keeps `gnome-shell-theme.gresource.big` unchanged.
GNOME 51 uses `gnome-shell-theme-51.gresource.big`. The matching `.default`
bundle provides the pristine theme for `gdm-settings` compatibility, avoiding
the old unversioned backup after a major upgrade.

The GNOME 51 base comes from Arch Linux `gnome-shell 1:51.0-1`, extracted from
its signed package. Upstream: https://gitlab.gnome.org/GNOME/gnome-shell/-/tree/51.0

`gdm-51.css` only adds BigCommunity branding. Native control sizing, input-well
layout, RTL rules and web login remain upstream. High contrast is unchanged.

Rebuild after editing the overlay (run from the repository root):

```sh
gresource extract usr/share/gnome-shell/gnome-shell-theme.gresource.big \
  /org/gnome/shell/theme/fundo.jpg > /tmp/gdm-wallpaper.jpg
python tools/build-gdm-theme.py \
  usr/share/gnome-shell/gnome-shell-theme-51.gresource.default \
  /tmp/gdm-wallpaper.jpg \
  usr/share/gnome-shell/gnome-shell-theme-51.gresource.big
python -m unittest discover -s tests -v
```

When updating the upstream base, replace the versioned `.default` with the
pristine package resource and rebuild `.big`. Never use the live customized
resource as the upstream source. New Shell major versions require an explicit
selector entry and theme review; unsupported versions fail without replacing
the live resource.

Wallpaper synchronization writes only the selected major-version bundle.
Resource installation uses atomic rename to preserve running Shell mappings.
A new GDM process loads the theme; installing files does not refresh an
existing greeter. Never restart GDM while a user session is active without
approval.
