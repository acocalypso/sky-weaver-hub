# Upgrade

Before upgrading, check that Python is 3.11+ and Node matches `^22.22.2 || ^24.15.0 || >=26.0.0` (Node 24 recommended). Dependency updates can require a newer build/test runtime than the OS-provided Node package. `upgrade.sh` refreshes application dependencies; it does not upgrade Node itself. See [dependency maintenance](DEPENDENCIES.md) for compatibility decisions.

```bash
sudo ./upgrade.sh
```

The upgrade script backs up config/database, refreshes `/opt/skyweaver`, refreshes backend/frontend dependencies, copies systemd units, reapplies camera hardware groups and constrained service-control sudoers permissions for the `skyweaver` service user, reloads systemd, and restarts `skyweaver.target`. Backend `pip install` is skipped when the installed `backend/requirements.txt` is unchanged and the existing virtualenv has a `pip` executable. Frontend `npm ci` is skipped when installed `package.json` and `package-lock.json` are unchanged and `node_modules` exists. Set `SKYWEAVER_FORCE_PIP_INSTALL=1` to force a backend dependency reinstall, or `SKYWEAVER_FORCE_NPM_INSTALL=1` to force a frontend dependency reinstall.

If the configured primary camera adapter is `zwo`, `upgrade.sh` also installs Debian package `libasi`, installs the USB udev permission rule, and verifies `libASICamera2.so` is available. It can also install `libASICamera2.so` from `SKYWEAVER_ZWO_SDK_URL` when the distro package is unavailable.

The script stops services, backs up config and database, updates code under `/opt/skyweaver`, refreshes backend/frontend dependencies, updates systemd units and service-control permissions, and restarts `skyweaver.target`.

The API, capture daemon, and worker run pending SQLite schema migrations automatically on startup. To inspect or apply migrations manually from a checkout:

```bash
cd backend
python -m skyweaver.migrate status
python -m skyweaver.migrate upgrade
```

Migrations are idempotent and recorded in the local `schema_migrations` table.
