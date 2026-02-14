# EQ Advisor Cache Directory

This directory contains all persistent cached data for EQ Advisor, including IEM frequency responses, target curves, and PEQ profiles.

## Directory Structure

```
cache/
├── fr/                 # IEM frequency response measurements
│   └── {iem}/
│       ├── default.csv           # Default variant (most common config)
│       └── {variant}.csv         # Alternative variants (nozzles, tips, etc.)
│
├── targets/            # AutoEQ target curves
│   └── {target}.csv              # Flat structure (no variants)
│
└── peq/                # PEQ profiles (device + IEM + variant + profile)
    └── {device}/
        ├── flat.json             # Device-level bypass (all filters off)
        └── {iem}/
            └── {variant}/
                └── {profile}.json
```

## Naming Conventions

### Normalization

All names are normalized to lowercase with hyphens:
- Spaces → hyphens: `Moondrop Blessing 3` → `moondrop-blessing-3`
- Underscores → hyphens: `Moondrop_Blessing_3` → `moondrop-blessing-3`
- Special characters preserved: `Aful Performer5+2` → `aful-performer5+2`

### IEM Variants

Variants represent different physical configurations of the same IEM model:
- **Nozzles:** `red-nozzle`, `blue-nozzle`, `brass-nozzle`, `steel-nozzle`
- **Tips:** `foam-tips`, `silicone-tips`, `spinfit-tips`
- **Insertion:** `shallow`, `deep`, `standard`
- **Switches/Settings:** `bass-boost-on`, `switch-1-on`, `dip-switch-2`
- **Default:** Always `default` for the most common/recommended configuration

### PEQ Profiles

Profile names describe the tuning goal or target:
- **Target-based:** `harman_ie_2019`, `diffuse_field`, `ief_neutral`
- **Preference-based:** `bass_boost`, `vocal_emphasis`, `gaming`, `v_shaped`
- **Custom:** Any descriptive name: `warm_balanced`, `bright_analytical`

## File Formats

### Frequency Response (FR)

CSV format with `frequency,raw` columns:
```csv
frequency,raw
20.3,102.32
20.6,102.29
...
```

### Target Curves

Same CSV format as FR data.

### PEQ Profiles

JSON format:
```json
{
  "name": "Harman IE 2019 Target",
  "pregain": -3.2,
  "filters": [
    {"freq": 100, "gain": 2.5, "q": 1.41, "type": "PK"},
    {"freq": 1000, "gain": -1.5, "q": 0.7, "type": "LSQ"}
  ]
}
```

Filter types: `PK` (peak), `LSQ` (low shelf), `HSQ` (high shelf)

## Metadata Files

Each IEM directory MAY contain a `.metadata.json` file tracking data provenance:

```json
{
  "canonical_name": "moondrop-blessing-3",
  "display_name": "Moondrop Blessing 3",
  "sources": [
    {
      "database": "crinacle",
      "original_name": "Moondrop Blessing 3",
      "file": "Moondrop_Blessing_3",
      "variant": "default",
      "fetched": "2026-02-14T10:30:00Z",
      "url": "https://crinacle.com/graphs/iems/graphtool/"
    }
  ],
  "variants": ["default", "red-nozzle", "blue-nozzle"]
}
```

## Cache Behavior

All tools follow a **cache-first** pattern:

1. **Check cache** - Look in `cache/` first
2. **Fetch if missing** - Download from remote source (squig.link, etc.)
3. **Store in cache** - Save fetched data for future use
4. **Never delete** - Cached data persists across sessions

## Measurement Rigs

**Current status:** Measurement rig differences (5128 vs 711 vs IEC60318-4) are **intentionally ignored**.

**Rationale:**
- Most databases use consistent rigs within each database
- Rig compensation requires complex calibration curves
- For consumer use, rig differences < IEM unit variation
- Users typically don't know which rig was used

**Future enhancement:**
```
cache/fr/{iem}/{variant}/{rig}.csv

Example:
cache/fr/moondrop-blessing-3/default/5128.csv
cache/fr/moondrop-blessing-3/default/711.csv
```

With metadata tracking:
```json
{
  "variant": "default",
  "measurements": {
    "5128": {"source": "crinacle", "fetched": "2026-02-14"},
    "711": {"source": "super_review", "fetched": "2026-02-15"}
  }
}
```

## Migration Notes

**From old structure:**
- `tools/squiglink/frequency_responses/` → `cache/fr/`
- `tools/autoeq/targets/` → `cache/targets/`
- `eq/{device}/` → Partially migrated to `cache/peq/{device}/`

**Manual migration needed:**
- Old `eq/` profiles without clear IEM association need manual review
- Assign each profile to appropriate `cache/peq/{device}/{iem}/{variant}/` path
- See `eq/` directory for remaining unmigrated profiles

## Version Control

**.gitignore rules:**
```
# Ignore all cache data (user-specific)
cache/

# EXCEPT: Ship default/example data
!cache/fr/moondrop-blessing-3/
!cache/targets/
!cache/peq/*/flat.json
```

This ensures shipped examples are tracked while user data stays local.

## Examples

### Complete workflow structure

```
cache/
├── fr/
│   └── moondrop-blessing-3/
│       ├── default.csv                    # Main measurement
│       ├── red-nozzle.csv                 # Red nozzle variant
│       └── .metadata.json                 # Source tracking
│
├── targets/
│   ├── harman-ie-2019.csv
│   └── diffuse-field-5128.csv
│
└── peq/
    ├── tanchjim-fission/
    │   ├── flat.json                      # Device bypass
    │   └── moondrop-blessing-3/
    │       ├── default/
    │       │   ├── harman_ie_2019.json   # AutoEQ to Harman
    │       │   ├── bass_boost.json        # Custom bass boost
    │       │   └── gaming.json            # Gaming profile
    │       └── red-nozzle/
    │           └── harman_ie_2019.json    # AutoEQ for red nozzle
    │
    └── qudelix-5k/
        ├── flat.json
        └── moondrop-blessing-3/
            └── default/
                └── harman_ie_2019.json
```

### Usage paths

**Get FR data:**
```python
fr_path = "cache/fr/moondrop-blessing-3/default.csv"
```

**Get target curve:**
```python
target_path = "cache/targets/harman-ie-2019.csv"
```

**Get PEQ profile:**
```python
peq_path = "cache/peq/tanchjim-fission/moondrop-blessing-3/default/harman_ie_2019.json"
```

**Device flat:**
```python
flat_path = "cache/peq/tanchjim-fission/flat.json"
```

---

Last updated: 2026-02-14
