# Migration From Allsky

Detection endpoint:

```bash
GET /api/v1/migration/allsky/detect
```

Preview endpoint:

```bash
POST /api/v1/migration/allsky/preview
```

Sky Weaver maps Allsky angle settings to `sun_angle`, day/night settings to camera profiles, public page behavior to `/public`, and retention settings to storage retention. Phase 1 does not delete or mutate original Allsky data.
