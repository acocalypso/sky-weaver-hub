# Install

Primary target is Raspberry Pi OS Bookworm 64-bit.

```bash
sudo ./install.sh
```

The installer detects OS and architecture, installs apt dependencies including Node/npm and Python, creates the `skyweaver` system user, creates `/opt/skyweaver`, `/etc/skyweaver`, `/var/lib/skyweaver`, and `/var/log/skyweaver`, builds the frontend, creates the Python virtualenv, installs systemd units, and starts `skyweaver.target`.

Use `SKYWEAVER_DRY_RUN=1 ./install.sh` to inspect commands without root privileges or filesystem writes.

For CI and development validation, `bash scripts/test_install.sh` runs the installer with temporary paths and mocked system tools. It verifies dry-run behavior and confirms a repeated install keeps the existing `skyweaver.env` instead of rotating secrets.
