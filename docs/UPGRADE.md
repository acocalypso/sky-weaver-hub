# Upgrade

```bash
sudo ./upgrade.sh
```

The upgrade script backs up config/database, refreshes `/opt/skyweaver`, reinstalls Python/frontend dependencies, copies systemd units, reapplies camera hardware groups and constrained service-control sudoers permissions for the `skyweaver` service user, reloads systemd, and restarts `skyweaver.target`.

If the configured primary camera adapter is `zwo`, `upgrade.sh` also installs ZWO USB/build dependencies, installs the USB udev rules, keeps a ZWO config directory available, and uses `camera-zwo-asi` from backend requirements. It can also install `libASICamera2.so` from `SKYWEAVER_ZWO_SDK_URL` when native SDK support is desired.

The script stops services, backs up config and database, updates code under `/opt/skyweaver`, refreshes backend/frontend dependencies, updates systemd units and service-control permissions, and restarts `skyweaver.target`.
