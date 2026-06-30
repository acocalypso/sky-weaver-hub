# Migration From Allsky

Detection endpoint:

```bash
GET /api/v1/migration/allsky/detect
```

Preview endpoint:

```bash
POST /api/v1/migration/allsky/preview
```

Import endpoint:

```bash
POST /api/v1/migration/allsky/import
```

Job and rollback endpoints:

```bash
GET /api/v1/migration/jobs/{job_id}
POST /api/v1/migration/jobs/{job_id}/rollback
```

Current import support copies recognized Allsky capture images into Sky Weaver image storage, imports dark frames into Sky Weaver dark-frame storage, imports keograms, startrails, and timelapses as generated night products, and preserves overlay image assets in Sky Weaver-owned migration storage. The scanner excludes Allsky web, documentation, config, and overlay asset trees so UI logos, placeholders, thumbnails, and documentation screenshots are not imported as sky captures. It also imports a conservative subset of settings when detected: observatory name/location/timezone, schedule sun angle, public page intent, public product visibility, storage retention, processing toggles, day/night profile capture/save/interval/exposure/gain, end-of-night product toggles, camera hints, and basic overlay text settings. Every imported row records migration provenance in metadata, including the import job id and original file path. Import jobs update progress and return a compact import log. Rollback deletes only Sky Weaver-created rows and copied files for that import job and restores the previous Sky Weaver settings snapshot.

Original Allsky data is never deleted or modified.

Current limitations:

- not every Allsky setting has a one-to-one Sky Weaver equivalent yet
- dark-frame processing/subtraction is not implemented yet
- overlay image/logo assets are preserved but not rendered by the text overlay module yet
- camera hints are stored as migration hints and do not create or replace hardware camera adapters
