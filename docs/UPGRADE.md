# Upgrade

```bash
sudo ./upgrade.sh
```

The script stops services, backs up config and database, updates code under `/opt/skyweaver`, refreshes backend/frontend dependencies, updates systemd units, and restarts `skyweaver.target`.
