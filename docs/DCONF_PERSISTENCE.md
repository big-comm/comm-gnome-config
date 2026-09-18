# GNOME persistence protocol 1

`dconf_persistence.py` owns validation, generation history and crash recovery.
Big Gnome Center, the monitor, final save, first boot and pre-Shell migration
share `~/.config/dconf/big-gnome-center-layout.lock`. Never unlink this flock
file. The runtime PID marker remains a compatibility guard, not a mutex.

## Files and commit order

- `settings.gnome`: readable dconf text export.
- `settings.gnome.state.json`: protocol version, three distinct checksummed
  text generations, pending transaction and next-login staging state.
- `settings.gnome.bak`, `.bak.2`: exports of preceding valid generations.
- `settings.gnome.big-gnome-center.sha256`: final-save protection; the legacy
  `.layout-switcher.sha256` name is also recognized.

Capture a valid baseline and durably mark the transaction before live writes.
Publish exports using unique temporary files, file fsync, rename and directory
fsync. Commit the generation record last. A crash before commit retains the
preceding generation. A failed or interrupted application prevents monitor and
logout snapshots from promoting partial live settings.

Recovery intentionally does not reset the live Shell's entire database.
Successful layout reapplication or the next login clears quarantine. Until
then, later live changes are not automatically saved. The application reports
this condition; background failures are recorded on stderr/journal.

Login validates candidates before resetting dconf. Legacy installations can
recover a missing, empty or invalid primary from `.bak`. Once migrated, the
checksummed history is authoritative: valid-syntax truncation of the export
cannot silently replace it. If no candidate is valid, keep live dconf intact
and return failure. Failed login loads attempt to restore the captured live
database; unsuccessful recovery retains the journal for another login.

## Editing and restoring text

Keep a reviewed copy outside the managed exports. Import it for the next login:

```sh
python /usr/share/comm-gnome-config/dconf_persistence.py import /path/to/reviewed-settings.txt
```

Import validates GVariant values, preserves staging against the old session
and can repair damaged metadata. Rejected metadata is archived alongside it.
An intentional minimal file is accepted; no arbitrary key-count threshold.
Back up the entire `~/.config/dconf` directory to retain generation history.
Do not directly edit managed exports and expect checksum validation to accept
them automatically. Import does not change the current live desktop.

## Deployment and limits

Deploy the matching Big Gnome Center and comm-gnome-config updates together.
Reopen Big Gnome Center after updating its Python modules. Before an apply,
it refreshes the existing sync service under the writer lock and PID guard,
retiring scripts loaded before the update without logging out. Failure to
refresh prevents the application. Inactive services remain inactive.

Automatic login replay is for the pre-Shell session startup path only.
The recovery CLI must not be used to reset dconf while Shell is running.
Text integrity cannot prove that a legacy unchecksummed file was never
truncated. Hardware/filesystem faults, all-generation loss, external writers
that ignore the lock and runtime extension recovery remain separate limits.
No claim of immunity to every power-loss or hardware failure.

## Checks

```sh
python -m unittest discover -s tests -v
bash -n usr/bin/dconf-sync-monitor-gnome usr/bin/dconf-sync-stop-gnome usr/bin/startgnome-community
```

Native regression gates use real dconf, a private bus/profile/home, an isolated
test account and injected process/command failures. Helper replies are mocked;
they do not establish visual Shell teardown/recovery or power-loss durability.
