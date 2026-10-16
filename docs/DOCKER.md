# Docker and Docker Compose

Sky Weaver runs as three non-root containers: the API (including the compiled web UI), capture daemon, and processing worker. They share named volumes for SQLite, images/products, configuration and logs. The same image runs each role. No external database or cloud account is required after pulling the image.

Images: `ghcr.io/acocalypso/sky-weaver-hub`, built for `linux/amd64` and `linux/arm64` (64-bit Raspberry Pi OS). ARMv7/32-bit Pi OS is not included. Container support does not establish real-camera acceptance.

## Start

Install Docker Engine with the Compose plugin, or Docker Desktop using Linux containers. Use a current Compose release supporting `--wait` and health-based dependencies.

```bash
git clone https://github.com/acocalypso/sky-weaver-hub.git
cd sky-weaver-hub
cp .env.docker.example .env
```

Edit `.env`: set `SKYWEAVER_SECRET_KEY` to a random value of at least 32 characters and set a strong `SKYWEAVER_ADMIN_PASSWORD`. Generate a secret with `python -c "import secrets; print(secrets.token_hex(32))"`. On PowerShell use `Copy-Item .env.docker.example .env` for the copy. Quote values containing `$` or `#` with single quotes in `.env` so Compose treats them literally. Keep this file private and backed up; it is ignored by Git and excluded from the image context.

```bash
docker compose pull
docker compose up -d --no-build --wait
```

Open `http://localhost:8765`, sign in with the configured username/password, and finish first setup. API docs are at `/api/docs`. Bootstrap environment values initialize a new database; changing them later does not reset an existing password or overwrite saved observatory/camera settings.

The port binds to loopback by default. For trusted LAN access, set `SKYWEAVER_BIND_ADDRESS=0.0.0.0` in `.env`. Public viewing defaults to disabled; enable it during setup if desired. The default camera is mock, for development and validation.

If GHCR returns an authentication error, the package may still be private: the repository owner can make it public in GitHub's package settings. For private pulls, authenticate to `ghcr.io` with a token that has `read:packages`; do not put a registry token in Compose or commit it.

## Build locally

```bash
docker compose build api
docker compose up -d --no-build --wait
```

Building `api` produces the shared image used by all three services. To keep it separate from registry images, set `SKYWEAVER_IMAGE=skyweaver:local` in `.env` first. The multi-stage build uses Node 24 for the web UI and Python 3.12/Debian Bookworm for runtime. ffmpeg, fonts, rsync and SSH client tools are included. Node and local runtime data are excluded from the final image.

## Manage and update

```bash
docker compose ps
docker compose logs -f --tail=100
docker compose restart capture worker
# Back up first, then update:
docker compose pull
docker compose up -d --no-build --wait
```

`latest` follows successful builds on `main`. `main`, `sha-<short-commit>` and pushed `v*` version tags are also published. Use an immutable digest (`image@sha256:...`) for reproducible deployments. Containers should all run the same image version.

`docker compose down` removes containers but preserves named volumes. Do not add `--volumes` to an observatory shutdown unless you intend to delete its stored data. Keep the same Compose project name so existing volumes are reused. Never run two stacks, workers or capture daemons against the same data volume; these services are singletons.

The API health check gates initial daemon/worker startup. Capture/worker health checks verify ownership of their kernel singleton locks; database heartbeats also report activity in Health. This avoids falsely rejecting long captures or video jobs because they delay heartbeat updates. Docker restarts exited services; an unhealthy status by itself does not restart a live process. Health checks do not prove camera readiness or a complete capture-to-product flow.

In container mode, Health identifies services as Docker-managed and hides systemd start/stop/restart actions. Admin service-control API calls return HTTP 409; use Compose on the host. Host Wi-Fi, time changes, systemd journals and installer operations remain host responsibilities. The Docker socket and host control interfaces are not mounted.

## Storage and backup

Compose uses `data`, `config` and `logs` named volumes, owned by UID/GID `10001:10001`. Web assets live in `/app/web` inside the image, so upgrades refresh the UI even when data volumes persist. Native installations retain their existing `data/web` default.

For a consistent backup, stop all three services and copy/archive all three volumes plus `.env`. Restore to empty volumes with the same ownership, image version and secret key before starting. The secret key is needed to decrypt stored upload credentials. Compose does not provide an automated backup/restore service. Downgrading an image after database migrations is not a substitute for restoring the matching database backup.

Bind mounts are possible with a local Compose override, but create their directories and assign UID/GID 10001 first on Linux. Permission failures stop startup; containers do not recursively change ownership of host data. Keep the SQLite data volume on local storage, not an NFS/SMB share. To import an existing installation, use an offline backup/copy; do not mount a live native database into a second stack.

## Cameras and external files

The portable image supports mock capture immediately. It does not bundle Raspberry Pi `rpicam` binaries or ZWO's SDK. Keep the native installer for an existing validated Pi camera deployment.

For CSI cameras, build a host-compatible image containing the matching rpicam/libcamera stack and configure explicit media/video/DMA device mappings and supplemental groups in a local override. Copying a host binary alone is insufficient because libraries, tuning files and kernel interfaces must match. For ZWO, install a matching-architecture SDK/library in a derived image, configure host USB permissions, and expose the necessary USB devices. These hardware configurations require acceptance on the actual host; they are not validated by mock CI. Do not use privileged mode as a default.

Allsky source directories and filesystem upload destinations must be mounted explicitly, using identical container paths in the services that consume them. Mount migration sources read-only. SSH uploads need a deliberately provisioned known-hosts file and any required keys readable by UID 10001. Existing host paths, credentials and devices are not automatically available inside containers.

## GitHub image builds

`.github/workflows/docker.yml` builds and smoke-tests the stack for pull requests, main pushes, version tags and manual runs. The smoke test authenticates, checks UI deep links, queues a mock image capture, generates/downloads a keogram and an ffmpeg timelapse through the real services, recreates containers, and checks persisted files and database records.

After smoke passes, main/tag/manual runs build both architectures and publish to GHCR using GitHub's built-in `GITHUB_TOKEN` with `packages: write`. No Docker Hub secret is needed. Pull requests do not publish images. The repository/package must permit Actions publishing; package visibility is managed separately in GitHub. Docker's official [multi-platform build](https://docs.docker.com/build/ci/github-actions/multi-platform/) and [registry publishing](https://docs.docker.com/build/ci/github-actions/push-multi-registries/) documentation informed this setup via Context7.

The smoke script creates test data and is intended only for disposable stacks: `python scripts/test_docker.py`, followed after recreation by `python scripts/test_docker.py --check-persistence`. It reads test credentials from the environment and stores only artifact IDs in ignored `.tmp/docker-smoke.json`.
