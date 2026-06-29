# Security

- Change the bootstrap password immediately.
- Passwords are hashed with bcrypt and must be 72 bytes or fewer.
- Failed login and first-setup completion attempts are rate-limited in-process per local database, client host, and account/user.
- Login and first-setup failures, rate-limit blocks, and recovery after previous failures are logged to the local `auth` log source without storing passwords or API secrets.
- Successful privileged changes are logged to the local `security` log source, including setup completion, password changes, user lifecycle, API-key lifecycle, settings, schedule, camera, and camera-profile changes.
- Security audit contexts record actor metadata, client host/user agent, target identifiers, scopes, and changed field/key names. They must not store submitted passwords, raw API keys, key hashes, or secret setting values.
- API keys are hashed and only shown once.
- Public pages must not expose admin controls.
- Camera adapters use subprocess argv lists.
- Custom command execution remains disabled until sandboxing is configured.
- Support bundles redact secrets from `/etc/skyweaver/skyweaver.env`.
