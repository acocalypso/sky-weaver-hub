# Install

Primary target is Raspberry Pi OS Bookworm 64-bit.

```bash
sudo ./install.sh
```

The installer detects OS and architecture, installs apt dependencies, creates the `skyweaver` system user, creates `/opt/skyweaver`, `/etc/skyweaver`, `/var/lib/skyweaver`, and `/var/log/skyweaver`, builds the frontend, creates the Python virtualenv, installs systemd units, and starts `skyweaver.target`.

Use `SKYWEAVER_DRY_RUN=1 sudo ./install.sh` to inspect commands.
