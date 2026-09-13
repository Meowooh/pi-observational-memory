# Experimental SoL-Pi composition

This fork adds an opt-in seam for an external compaction trigger. It does not change Observer, Reflector or Dropper defaults. The measured pilot and its limitations are in [`benchmarks/sol-pi`](../benchmarks/sol-pi/README.md); cost savings are not guaranteed.

Use the SoL-Pi revision pinned in that experiment's manifest. Add the following key to the existing project's `.pi/settings.json`:

```json
{
  "observational-memory": {
    "proactiveCompaction": false
  }
}
```

Keep `passive` at its default `false`. Create `.pi/sol-pi.json` in the project:

```json
{
  "version": 1,
  "actionFusion": false,
  "observationPack": true,
  "evidencePreservingReducer": false,
  "onlineContextCompact": true,
  "cacheWriteReadRatio": 12.5
}
```

Load OM followed by SoL-Pi in that project, using their actual checkout paths:

```sh
rtk proxy pi \
  -e /absolute/path/to/pi-observational-memory/src/index.ts \
  -e /absolute/path/to/SoL-Pi/src/sol-pi/index.ts
```

Load each extension once. If the packages are already installed in Pi, use their installed registration instead of duplicating `-e` entries. If using a `--tools` allowlist, include `update_plan`, `recall` and `obs_recall` along with the normal file/shell tools.

The main agent maintains a working plan with `update_plan`. A completed step lets SoL-Pi consider compaction through its economic gate. OM continues to build memory asynchronously and supplies its stored-memory summary when Pi compacts. Pi's native context-pressure compaction remains available. ObservationPack keeps large tool results in full for the first two projections and then substitutes recallable placeholders, without altering the original session ledger that OM observes.

The default SoL-Pi gate assumes a write/read ratio of 12.5 and a 1,000-token summary. These are estimates, not a measured OM summary size or verified route-specific invoice. The pilot does not justify changing worker thresholds or automatically enabling this composition in existing user sessions.
