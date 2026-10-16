# Install

Primary target is Raspberry Pi OS Bookworm 64-bit.

The current dependency set requires Python 3.11+ and a Node version matching `package.json`: `^22.22.2 || ^24.15.0 || >=26.0.0`. Node 24 is the recommended build/test runtime and is used in CI. Check `python3 --version` and `node --version` before installation. The installer uses configured apt repositories for Node/npm; it does not provision a newer Node release when the OS package is too old. Configure a suitable package source/runtime before running the installer in that case. Bookworm's Python 3.11 meets the Python requirement.

```bash
sudo ./install.sh
```

The installer detects OS and architecture, installs apt dependencies including Node/npm and Python, creates the `skyweaver` system user, adds it to available camera hardware groups (`video`, `render`, `input`, `gpio`, `i2c`, `spi`), creates `/opt/skyweaver`, `/etc/skyweaver`, `/var/lib/skyweaver`, and `/var/log/skyweaver`, builds the frontend, creates the Python virtualenv, installs systemd units, writes constrained sudoers rules for Sky Weaver service controls, browser-to-Pi time sync, and NetworkManager Wi-Fi operations, and starts `skyweaver.target`.

On a fresh interactive install, it asks for:

- admin username and password
- observatory name
- latitude and longitude
- timezone
- primary camera adapter
- public sky page enabled/disabled

The admin password is stored as a bcrypt hash in `/etc/skyweaver/skyweaver.env`, not as plaintext. Noninteractive installs use defaults or explicit `SKYWEAVER_*` environment values. Re-running the installer keeps the existing `skyweaver.env`.

## Local Pi access

The Settings page can sync Pi time from the browser clock for offline setups without RTC hardware. It can also scan and connect Wi-Fi networks through NetworkManager's `nmcli` using portable terse output parsing. The backend uses argument-array subprocess calls and admin-scoped API routes; the installer grants only the required `date` and `nmcli` sudoers command families. Wi-Fi password values are not returned by the API.

## ZWO ASI

When the configured primary camera adapter is `zwo`, `install.sh` and `upgrade.sh` install Debian package `libasi`, add a ZWO ASI udev permission rule, and use the native `libASICamera2.so` SDK library.

```bash
sudo SKYWEAVER_PRIMARY_CAMERA_ADAPTER=zwo ./install.sh
```

On Debian/Raspberry Pi OS, `libasi` is provided by the non-free archive. If the package is unavailable on your distribution, set `SKYWEAVER_ZWO_SDK_URL` to the official ZWO ASI Linux/Mac SDK archive before running install or upgrade. Use `SKYWEAVER_INSTALL_ZWO_SDK=0` only when you want to manage all ZWO setup outside Sky Weaver.

Use `SKYWEAVER_DRY_RUN=1 ./install.sh` to inspect commands without root privileges or filesystem writes.

For CI and development validation, `bash scripts/test_install.sh` runs the installer with temporary paths and mocked system tools. It verifies dry-run behavior, service-control sudoers generation, and confirms a repeated install keeps the existing `skyweaver.env` instead of rotating secrets.
