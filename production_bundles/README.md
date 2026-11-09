# Production Bundles

This directory tracks production software bundles (tar archives) available on the FCC CVMFS repository.

## Submitting a new bundle

Create a YAML file (any name, e.g. `my-submission.yml`) with a `bundles` list:

```yaml
bundles:
  # Bundle from a URL
  - bundle: my-software
    category: FCC-ee          # detector or top-level group
    subcategory: v01          # optional further subdivision
    version: "1.0"
    source-location: https://example.com/my-software-1.0.tar.gz
    readme: |
      Optional human-readable description of this version.

  # Bundle from a local tarball committed into this PR
  - bundle: another-tool
    category: FCC-hh
    version: "2.3"
    source-location: another-tool-2.3.tar.gz   # bare filename, no ://
    # The file must exist at production_bundles/another-tool-2.3.tar.gz
    # in the PR. It will be removed from git history after merge.

  # Multiple files (downloaded individually)
  - bundle: multi-file-bundle
    category: Common
    version: "1.0"
    source-location:
      - https://example.com/multi-file-bundle-1.0-part1.tar.gz
      - https://example.com/multi-file-bundle-1.0-part2.tar.gz

  # Optional: place extracted files in a subdirectory within the version directory
  - bundle: nested-bundle
    category: FCC-ee
    version: "3.0"
    source-location: https://example.com/nested-bundle-3.0.tar.gz
    directory: /data
```

Open a pull request. A workflow will automatically validate your submission and post a comment with the result.

**Rules:**
- The `summary_` prefix is reserved — do not use it for submission files.
- Each `bundle` + `category` + `subcategory` + `version` combination must be unique.
- `bundle`, `version`, `source-location`, and `category` are required for every entry.
- `subcategory` is optional; omit it when there is no meaningful subdivision.
- Local tarballs must be under 50 MB (GitHub hard-blocks files over 100 MB).
- Local `source-location` must be a bare filename (no `://`) with a supported extension:
  `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz`.

## What happens on merge

1. The action validates all entries (fails if any version already exists).
2. Each source is fetched: URL sources are downloaded; local tarballs are read from the repo.
3. A SHA-256 checksum is computed for each file.
4. A `tar -tvf` file listing is captured and saved in the GitHub Actions artifact so reviewers can inspect the archive contents.
5. Each entry is appended to its `summary_<bundle>.yml` file with the checksum and UTC timestamp.
6. Your submission file is deleted — the summary becomes the permanent record.
7. A GitHub Actions artifact (`production-bundles-pr-<N>`) is uploaded containing the resolved submission YAML, downloaded files, file listings, and `pr.txt`.
8. If any local tarballs were included, `git filter-repo` rewrites history to remove the blob entirely, then force-pushes `main`. The repo size does not grow.

## Directory structure

Summary files live under `production_bundles/<category>/[<subcategory>/]summary_<bundle>.yml`.
For example, `FCC-ee/v01/summary_my-software.yml` or `Common/summary_multi-file-bundle.yml`.

## Summary files

`summary_<bundle>.yml` files are the permanent record. They are append-only: existing version entries must never be modified or removed. Each version entry records `source-location`, `sha256`, and `added` (UTC datetime).
