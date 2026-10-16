# Security

- Change the bootstrap password immediately.
- Passwords are hashed with bcrypt and must be 72 bytes or fewer.
- Login rejects overlong passwords instead of authenticating their first 72 bytes; the limit applies to UTF-8 bytes, not character count.
- User JWTs require subject/expiry claims. Each authenticated request resolves the current stored user and role, so deletion and role changes affect existing sessions. Admin, operator and viewer scope mappings are documented in [API.md](API.md).
- Optional API-key expiration is enforced before recording usage. Invalid/timezone-free creation values are rejected; expired keys and invalid legacy expiry values cannot authenticate.
- API keys cannot call the current-user password-change endpoint.
- Failed login and first-setup completion attempts are rate-limited in-process per local database, client host, and account/user.
- Login and first-setup failures, rate-limit blocks, and recovery after previous failures are logged to the local `auth` log source without storing passwords or API secrets.
- Successful privileged changes are logged to the local `security` log source, including setup completion, password changes, user lifecycle, API-key lifecycle, settings, schedule, camera, and camera-profile changes.
- Security audit contexts record actor metadata, client host/user agent, target identifiers, scopes, and changed field/key names. They must not store submitted passwords, raw API keys, key hashes, or secret setting values.
- API keys are hashed and only shown once.
- Remote target configs are stored locally as a Fernet encrypted envelope derived from `SKYWEAVER_SECRET_KEY`; keep that key stable and protected or existing encrypted upload targets cannot be decrypted.
- Public pages must not expose admin controls.
- Camera adapters use subprocess argv lists.
- Custom command execution remains disabled until sandboxing is configured.
- Support bundles redact secrets from `/etc/skyweaver/skyweaver.env`.

These checks do not add server-side logout revocation or invalidate every previously issued token when a password changes. Those session-lifecycle policies remain separate work; do not describe all token revocation as implemented.
