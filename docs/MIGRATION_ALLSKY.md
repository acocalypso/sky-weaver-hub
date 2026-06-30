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

Current import support copies recognized Allsky capture images into Sky Weaver image storage, imports dark frames into Sky Weaver dark-frame storage, and imports keograms, startrails, and timelapses as generated night products. The scanner excludes Allsky web, documentation, config, and overlay asset trees so UI logos, placeholders, thumbnails, and documentation screenshots are not imported as sky captures. It also imports a conservative subset of settings when detected: observatory name/location/timezone, schedule sun angle, public page intent, camera hints, and basic overlay text settings. Every imported row records migration provenance in metadata, including the import job id and original file path. Import jobs update progress and return a compact import log. Rollback deletes only Sky Weaver-created rows and copied files for that import job and restores the previous Sky Weaver settings snapshot.

Original Allsky data is never deleted or modified.

Current limitations:

- only selected Allsky settings are translated
- dark-frame processing/subtraction is not implemented yet
- overlay image/logo assets are not imported yet
- camera hints are stored as migration hints and do not create or replace hardware camera adapters
