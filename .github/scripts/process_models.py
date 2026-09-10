#!/usr/bin/env python3
"""
Process fcc_models package YAML files on PR merge (or dry-run on PR open).

Each submission file contains a `packages` list. For each entry:
  - Validates required fields are present
  - Fails if the version already exists in the summary file

All entries in a file are validated before any summaries are written (atomic).
On success (non-dry-run), summaries are updated and the submission file is deleted.

Exit codes:
  0 — all good
  1 — one or more validation errors
"""

import sys
import os
import subprocess
import datetime
import hashlib
import json
import urllib.request
import urllib.error
import argparse
import yaml

REQUIRED_FIELDS = {"package", "version", "source-location"}


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def summary_path(models_dir, package_name):
    return os.path.join(models_dir, f"summary_{package_name}.yml")


def normalize_sources(entry):
    """Return source-location as a list regardless of whether it was a string or list."""
    src = entry["source-location"]
    return src if isinstance(src, list) else [src]


def download_file(url, dest_dir):
    """Download url into dest_dir; return (local_path, sha256_hex)."""
    filename = url.rsplit("/", 1)[-1] or "file"
    dest = os.path.join(dest_dir, filename)
    urllib.request.urlretrieve(url, dest)
    digest = hashlib.sha256()
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return dest, digest.hexdigest()


def validate_entry(entry, source_file):
    """Validate one package entry; return an error string or None."""
    missing = REQUIRED_FIELDS - set(entry.keys())
    if missing:
        return f"{source_file}: missing required fields: {sorted(missing)}"
    src = entry["source-location"]
    if not isinstance(src, (str, list)) or (isinstance(src, list) and not src):
        return f"{source_file}: `source-location` must be a URL string or a non-empty list of URLs"
    if "readme" in entry and not isinstance(entry["readme"], str):
        return f"{source_file}: `readme` must be a string"
    if "directory" in entry and not isinstance(entry["directory"], str):
        return f"{source_file}: `directory` must be a string"
    return None


def check_duplicate(models_dir, entry, source_file):
    """Return an error string if the version already exists in the summary, else None."""
    package = entry["package"]
    version = str(entry["version"])
    spath = summary_path(models_dir, package)
    if os.path.exists(spath):
        summary = load_yaml(spath)
        existing = [str(v["version"]) for v in summary.get("versions", [])]
        if version in existing:
            return (
                f"{source_file}: version {version!r} of package {package!r} "
                f"already exists in {spath}"
            )
    return None


def get_inherited_readme(models_dir, package):
    """Return readme from the most recent version in the summary, or None."""
    spath = summary_path(models_dir, package)
    if not os.path.exists(spath):
        return None
    summary = load_yaml(spath)
    versions = summary.get("versions", [])
    if not versions:
        return None
    return versions[-1].get("readme")


def update_summary(models_dir, entry, sha256_info, added):
    """Append the entry to its summary file, creating it if needed."""
    package = entry["package"]
    version = str(entry["version"])
    spath = summary_path(models_dir, package)

    if os.path.exists(spath):
        summary = load_yaml(spath)
    else:
        summary = {"package": package, "versions": []}

    record = {
        "version": version,
        "source-location": entry["source-location"],
        "sha256": sha256_info,
        "added": added,
    }
    if "directory" in entry:
        record["directory"] = entry["directory"]
    if "readme" in entry:
        record["readme"] = entry["readme"]
    summary["versions"].append(record)

    with open(spath, "w") as f:
        yaml.dump(summary, f, default_flow_style=False, sort_keys=False)

    return spath


def process_file(models_dir, submission_file, dry_run, artifact_dir=None):
    """
    Validate all entries in submission_file atomically, then (if not dry_run)
    inherit missing readmes from summaries, write summaries, write the resolved
    submission YAML to artifact_dir (if given), and delete the submission file.

    Returns (ok: bool, messages: list[str], updated_summaries: list[str])
    """
    data = load_yaml(submission_file)

    if "packages" not in data or not isinstance(data["packages"], list):
        return False, [f"{submission_file}: must contain a top-level `packages` list"], []

    entries = data["packages"]
    if not entries:
        return False, [f"{submission_file}: `packages` list is empty"], []

    # --- validation pass (touch nothing yet) ---
    errors = []
    for entry in entries:
        err = validate_entry(entry, submission_file)
        if err:
            errors.append(err)
            continue
        err = check_duplicate(models_dir, entry, submission_file)
        if err:
            errors.append(err)

    if errors:
        return False, errors, []

    # --- write pass ---
    messages = []
    updated_summaries = []

    if not dry_run:
        # Inherit readme from most recent summary version when not specified
        for entry in entries:
            if "readme" not in entry:
                inherited = get_inherited_readme(models_dir, entry["package"])
                if inherited:
                    entry["readme"] = inherited
                    messages.append(f"  inherited readme for {entry['package']} v{entry['version']}")

        # Download all source files; collect checksums
        if artifact_dir:
            os.makedirs(artifact_dir, exist_ok=True)
        dl_dir = artifact_dir or os.path.join(os.path.dirname(submission_file), ".dl_tmp")
        os.makedirs(dl_dir, exist_ok=True)

        url_checksums = {}  # url → sha256_hex
        for entry in entries:
            subdir = entry.get("directory", "").lstrip("/")
            dest_dir = os.path.join(dl_dir, subdir) if subdir else dl_dir
            os.makedirs(dest_dir, exist_ok=True)
            for url in normalize_sources(entry):
                if url in url_checksums:
                    continue
                try:
                    _, chksum = download_file(url, dest_dir)
                    url_checksums[url] = chksum
                    messages.append(f"  downloaded {url} (sha256: {chksum[:12]}…)")
                except urllib.error.URLError as exc:
                    return False, messages + [f"  failed to download {url}: {exc}"], []

        added = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

        # Annotate entries with sha256 + added so the artifact YAML is fully resolved
        for entry in entries:
            sources = normalize_sources(entry)
            if isinstance(entry["source-location"], str):
                entry["sha256"] = url_checksums[entry["source-location"]]
            else:
                entry["sha256"] = [url_checksums[u] for u in sources]
            entry["added"] = added

        # Write resolved submission YAML and JSON sidecar to artifact dir
        if artifact_dir:
            dest = os.path.join(artifact_dir, os.path.basename(submission_file))
            with open(dest, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            json_dest = dest.rsplit(".", 1)[0] + ".json"
            with open(json_dest, "w") as f:
                json.dump(data, f, indent=2)

        for entry in entries:
            spath = update_summary(models_dir, entry, entry["sha256"], added)
            updated_summaries.append(spath)
            messages.append(f"  updated {spath}")
        os.remove(submission_file)
        messages.append(f"  removed {submission_file}")
    else:
        for entry in entries:
            sources = normalize_sources(entry)
            src_display = sources[0] if len(sources) == 1 else f"{len(sources)} files"
            messages.append(
                f"  OK: {entry['package']} v{entry['version']} ({src_display})"
            )

    return True, messages, updated_summaries


def _git_show(ref, path):
    """Return file content at a git ref, or None if not found."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True,
    )
    return result.stdout if result.returncode == 0 else None


def process_summary_file(models_dir, summary_file, dry_run, artifact_dir=None, base_ref=None):
    """
    Handle a directly-edited summary file.

    Rules:
    - Existing version entries must not be modified or removed (append-only).
    - New version entries are downloaded, checksummed, and written to artifact_dir.

    Returns (ok: bool, messages: list[str], updated_summaries: list[str])
    """
    current = load_yaml(summary_file)
    if not isinstance(current, dict) or "versions" not in current:
        return False, [f"{summary_file}: must have a top-level 'versions' list"], []

    package = current.get("package", "")
    expected = os.path.basename(summary_file)[len("summary_"):-len(".yml")]
    if package != expected:
        return False, [
            f"{summary_file}: 'package' field {package!r} does not match filename (expected {expected!r})"
        ], []

    current_versions = current.get("versions", [])
    current_by_ver = {str(v["version"]): v for v in current_versions}

    # Determine old state from base_ref
    old_versions = []
    if base_ref:
        old_text = _git_show(base_ref, summary_file)
        if old_text:
            old_data = yaml.safe_load(old_text) or {}
            old_versions = old_data.get("versions", [])
    old_by_ver = {str(v["version"]): v for v in old_versions}

    # Immutability check: existing entries must be unchanged
    errors = []
    for ver_str, old_entry in old_by_ver.items():
        if ver_str not in current_by_ver:
            errors.append(
                f"{summary_file}: existing version {ver_str!r} was removed — "
                "summary files are append-only"
            )
        elif current_by_ver[ver_str] != old_entry:
            errors.append(
                f"{summary_file}: existing version {ver_str!r} was modified — "
                "summary files are append-only"
            )
    if errors:
        return False, errors, []

    # Find new version entries
    new_entries = [v for v in current_versions if str(v["version"]) not in old_by_ver]
    if not new_entries:
        return True, [f"{summary_file}: no new versions found (nothing to do)"], []

    # Validate new entries
    for ve in new_entries:
        synthetic = {
            "package": package,
            "version": ve.get("version", ""),
            "source-location": ve.get("source-location", ""),
        }
        for k in ("directory", "readme"):
            if k in ve:
                synthetic[k] = ve[k]
        err = validate_entry(synthetic, summary_file)
        if err:
            errors.append(err)
    if errors:
        return False, errors, []

    messages = []

    if dry_run:
        for ve in new_entries:
            sources = normalize_sources({"source-location": ve["source-location"]})
            src_display = sources[0] if len(sources) == 1 else f"{len(sources)} files"
            messages.append(f"  OK (new): {package} v{ve['version']} ({src_display})")
        return True, messages, []

    # Download files and fill in sha256 + added
    if artifact_dir:
        os.makedirs(artifact_dir, exist_ok=True)
    dl_dir = artifact_dir or os.path.join(os.path.dirname(summary_file), ".dl_tmp")
    os.makedirs(dl_dir, exist_ok=True)

    url_checksums = {}
    added = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    for ve in new_entries:
        subdir = ve.get("directory", "").lstrip("/")
        dest_dir = os.path.join(dl_dir, subdir) if subdir else dl_dir
        os.makedirs(dest_dir, exist_ok=True)
        for url in normalize_sources({"source-location": ve["source-location"]}):
            if url in url_checksums:
                continue
            try:
                _, chksum = download_file(url, dest_dir)
                url_checksums[url] = chksum
                messages.append(f"  downloaded {url} (sha256: {chksum[:12]}…)")
            except urllib.error.URLError as exc:
                return False, messages + [f"  failed to download {url}: {exc}"], []

        src = ve["source-location"]
        if isinstance(src, str):
            ve["sha256"] = url_checksums[src]
        else:
            ve["sha256"] = [url_checksums[u] for u in src]
        ve["added"] = added
        messages.append(f"  filled in sha256/added for {package} v{ve['version']}")

    # Write updated summary file (with sha256 + added filled in)
    with open(summary_file, "w") as f:
        yaml.dump(current, f, default_flow_style=False, sort_keys=False)

    # Write artifact JSON for the consumer (same format as submission-flow JSON sidecar)
    if artifact_dir:
        artifact_data = {
            "packages": [
                {
                    "package": package,
                    "version": str(ve["version"]),
                    "source-location": ve["source-location"],
                    "sha256": ve["sha256"],
                    "added": ve["added"],
                    **{k: ve[k] for k in ("directory", "readme") if k in ve},
                }
                for ve in new_entries
            ]
        }
        json_dest = os.path.join(artifact_dir, f"{package}.json")
        with open(json_dest, "w") as f:
            json.dump(artifact_data, f, indent=2)
        messages.append(f"  wrote artifact {json_dest}")

    return True, messages, [summary_file]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("submission_files", nargs="+", help="Submission or summary YAML files to process")
    parser.add_argument("--models-dir", default="fcc_models")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not write")
    parser.add_argument("--artifact-dir", default=None, help="Write resolved YAMLs/JSON here")
    parser.add_argument("--base-ref", default=None, help="Git ref for the before-state (used for summary immutability checks)")
    parser.add_argument(
        "--output-format",
        choices=["text", "markdown"],
        default="text",
        help="Output format (markdown for PR comments)",
    )
    args = parser.parse_args()

    all_ok = True
    all_updated_summaries = []
    report_lines = []

    for sfile in args.submission_files:
        if os.path.basename(sfile).startswith("summary_"):
            ok, messages, updated = process_summary_file(
                args.models_dir, sfile, args.dry_run, args.artifact_dir, args.base_ref
            )
        else:
            ok, messages, updated = process_file(args.models_dir, sfile, args.dry_run, args.artifact_dir)
        all_ok = all_ok and ok
        all_updated_summaries.extend(updated)

        if args.output_format == "markdown":
            icon = "✅" if ok else "❌"
            report_lines.append(f"{icon} **`{sfile}`**")
            for m in messages:
                report_lines.append(f"  - {m.strip()}")
        else:
            status = "OK" if ok else "FAILED"
            print(f"[{status}] {sfile}")
            for m in messages:
                print(m)

    if args.output_format == "markdown":
        header = (
            "### FCC Models — validation passed ✅"
            if all_ok
            else "### FCC Models — validation failed ❌"
        )
        note = (
            "_On merge: summaries will be updated and submission files removed._"
            if all_ok and args.dry_run
            else ""
        )
        print("\n".join([header, ""] + report_lines + (["", note] if note else [])))

    if not all_ok:
        sys.exit(1)

    # Emit updated summary paths for the workflow
    gho = os.environ.get("GITHUB_OUTPUT")
    if gho and all_updated_summaries:
        with open(gho, "a") as f:
            f.write(f"updated_summaries={' '.join(all_updated_summaries)}\n")


if __name__ == "__main__":
    main()
