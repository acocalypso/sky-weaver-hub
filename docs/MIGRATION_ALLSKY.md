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

Current import support copies Allsky images into Sky Weaver image storage and imports keograms, startrails, and timelapses as generated night products. Every imported row records migration provenance in metadata, including the import job id and original file path. Rollback deletes only Sky Weaver-created rows and copied files for that import job.

Original Allsky data is never deleted or modified.

Current limitations:

- selected Allsky settings are reported as unsupported rather than translated
- dark frames are not imported yet
- overlay assets are not imported yet
- camera hints/location migration is not implemented yet
