# Upgrade

```bash
sudo ./upgrade.sh
```

The upgrade script backs up config/database, refreshes `/opt/skyweaver`, reinstalls Python/frontend dependencies, copies systemd units, reapplies camera hardware groups and constrained service-control sudoers permissions for the `skyweaver` service user, reloads systemd, and restarts `skyweaver.target`.

The script stops services, backs up config and database, updates code under `/opt/skyweaver`, refreshes backend/frontend dependencies, updates systemd units and service-control permissions, and restarts `skyweaver.target`.
