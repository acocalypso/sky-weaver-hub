# Security

- Change the bootstrap password immediately.
- Passwords are hashed with bcrypt.
- API keys are hashed and only shown once.
- Public pages must not expose admin controls.
- Camera adapters use subprocess argv lists.
- Custom command execution remains disabled until sandboxing is configured.
- Support bundles redact secrets from `/etc/skyweaver/skyweaver.env`.
