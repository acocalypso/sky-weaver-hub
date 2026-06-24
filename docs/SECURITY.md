# Security

- Change the bootstrap password immediately.
- Passwords are hashed with bcrypt and must be 72 bytes or fewer.
- Failed login and first-setup completion attempts are rate-limited in-process per local database, client host, and account/user.
- API keys are hashed and only shown once.
- Public pages must not expose admin controls.
- Camera adapters use subprocess argv lists.
- Custom command execution remains disabled until sandboxing is configured.
- Support bundles redact secrets from `/etc/skyweaver/skyweaver.env`.
