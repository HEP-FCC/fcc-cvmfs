# FCC Models

This directory tracks data files available on the FCC CVMFS repository.

## Submitting a new model or version

Create a YAML file (any name, e.g. `my-submission.yml`) with a `packages` list:

```yaml
packages:
  # Single file
  - package: my-onnx-model
    version: "1.0"
    source-location: http://example.com/my-onnx-model-1.0.root
    readme: |
      Optional human-readable description of this version.
      Stored as README.txt alongside the files on CVMFS.
      Can also be a single URL pointing to external documentation:
    # readme: https://example.com/my-onnx-model/docs

  # Multiple files (downloaded individually)
  - package: another-model
    version: "2.3"
    source-location:
      - http://example.com/another-model-2.3.onnx
      - http://example.com/another-model-2.3-weights.bin

  # Optional: place files in a subdirectory within the version directory
  - package: delphes-card-fcc
    version: "4.0"
    source-location: http://example.com/delphes-card-fcc-4.0.tcl
    directory: /cards
```

The PR description is automatically saved as `pr.txt` in every version directory deployed from that PR.

Open a pull request. A workflow will automatically validate your submission and post a comment with the result.

**Rules:**
- The `summary_` prefix is reserved — do not use it for submission files.
- Each `package` + `version` combination must be unique across all submissions.
- All three fields (`package`, `version`, `source-location`) are required for every entry.

## What happens on merge

1. The action validates all entries (fails if any version already exists).
2. Each source file is downloaded and its SHA-256 checksum is computed.
3. Each entry is appended to its `summary_<package>.yml` file with the checksum and UTC download timestamp.
4. Your submission file is deleted — the summary becomes the permanent record.
5. A GitHub Actions artifact is uploaded containing the resolved submission YAML (with `sha256` and `added` filled in), the downloaded source files, and `pr.txt`.

## Adding a new version of an existing package

Use `new_version.py` to avoid writing the YAML by hand:

```bash
python fcc_models/new_version.py <package> <new-version>
```

This copies the source URLs from the most recent version in the summary file and appends a new entry. The workflow fills in the checksums and timestamp on merge. Commit `fcc_models/summary_<package>.yml` and open a PR.

## Summary files

`summary_<package>.yml` files are the permanent record of what is on CVMFS. They are append-only: existing version entries must never be modified or removed. New versions may be added via PR (using `new_version.py` or by editing the file directly). Each version entry records `source-location`, `sha256` (mirroring the structure of `source-location` — a string for a single file, a list for multiple), and `added` (UTC datetime of download).
