# Install

Primary target is Raspberry Pi OS Bookworm 64-bit.

```bash
sudo ./install.sh
```

The installer detects OS and architecture, installs apt dependencies including Node/npm and Python, creates the `skyweaver` system user, adds it to available camera hardware groups (`video`, `render`, `input`, `gpio`, `i2c`, `spi`), creates `/opt/skyweaver`, `/etc/skyweaver`, `/var/lib/skyweaver`, and `/var/log/skyweaver`, builds the frontend, creates the Python virtualenv, installs systemd units, writes a constrained sudoers rule for Sky Weaver service controls, and starts `skyweaver.target`.

On a fresh interactive install, it asks for:

- admin username and password
- observatory name
- latitude and longitude
- timezone
- primary camera adapter
- public sky page enabled/disabled

The admin password is stored as a bcrypt hash in `/etc/skyweaver/skyweaver.env`, not as plaintext. Noninteractive installs use defaults or explicit `SKYWEAVER_*` environment values. Re-running the installer keeps the existing `skyweaver.env`.

## ZWO ASI SDK

When the configured primary camera adapter is `zwo`, `install.sh` and `upgrade.sh` install USB runtime dependencies, add ZWO ASI udev rules, and look for `libASICamera2.so`. If the SDK library is already installed system-wide, Sky Weaver uses it. If not, set `SKYWEAVER_ZWO_SDK_URL` to the official ZWO ASI Linux/Mac SDK archive before running the installer or upgrade script:

```bash
sudo SKYWEAVER_PRIMARY_CAMERA_ADAPTER=zwo SKYWEAVER_ZWO_SDK_URL="https://example.com/ASI_linux_mac_SDK.zip" ./install.sh
```

The scripts copy the matching `libASICamera2.so` into `/opt/skyweaver/vendor/zwo/lib`, refresh the dynamic linker cache, and add `SKYWEAVER_ZWO_SDK_LIBRARY` to `skyweaver.env` when it is not already set. Use `SKYWEAVER_INSTALL_ZWO_SDK=0` only when you want to manage the SDK outside Sky Weaver.

Use `SKYWEAVER_DRY_RUN=1 ./install.sh` to inspect commands without root privileges or filesystem writes.

For CI and development validation, `bash scripts/test_install.sh` runs the installer with temporary paths and mocked system tools. It verifies dry-run behavior, service-control sudoers generation, and confirms a repeated install keeps the existing `skyweaver.env` instead of rotating secrets.
