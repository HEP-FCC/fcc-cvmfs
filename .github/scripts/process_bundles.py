#!/usr/bin/env python3
"""
Process production_bundles YAML files on PR merge (or dry-run on PR open).

Each submission file contains a `bundles` list. For each entry:
  - Validates required fields are present
  - Fails if the version already exists in the summary file

All entries in a file are validated before any summaries are written (atomic).
On success (non-dry-run), summaries are updated and the submission file is deleted.

source-location may be a URL string, a list of URL strings, or a bare filename
(no ://) for a tarball committed directly to production_bundles/ in the PR.
Local tarballs are removed from the working tree after processing; the caller
(the CI workflow) is responsible for rewriting git history to drop the blob.

Exit codes:
  0 — all good
  1 — one or more validation errors
"""

import sys
import os
import shutil
import subprocess
import datetime
import hashlib
import json
import urllib.request
import urllib.error
import argparse
import yaml

REQUIRED_FIELDS = {"bundle", "version", "source-location", "category"}
TARBALL_EXTENSIONS = (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def summary_path(models_dir, bundle_name, category, subcategory=None):
    if subcategory:
        return os.path.join(models_dir, category, subcategory, f"summary_{bundle_name}.yml")
    return os.path.join(models_dir, category, f"summary_{bundle_name}.yml")


def normalize_sources(entry):
    """Return source-location as a list regardless of whether it was a string or list."""
    src = entry["source-location"]
    return src if isinstance(src, list) else [src]


def is_local_source(src):
    """Return True if src is a local tarball path (no :// scheme)."""
    return isinstance(src, str) and "://" not in src


def _format_tar_listing(raw):
    """Reformat raw tar -tvf output to: <permissions>  <size>  <file>."""
    lines = []
    for line in raw.splitlines():
        parts = line.split()
        # GNU tar: perms user/group size date time name  (6+ fields)
        # BSD tar: perms nlinks user group size ...  name  (9 fields)
        # Either way $1=perms, last=name; size is $3 on GNU, $5 on BSD.
        if len(parts) < 4:
            continue
        perms = parts[0]
        name  = parts[-1]
        size  = parts[2] if "/" in parts[1] else parts[4]
        lines.append(f"{perms}  {int(size):>10}  {name}")
    return "\n".join(lines) + "\n"


def get_tar_listing(path):
    """Return a compact listing of a tarball: permissions, size, filename."""
    result = subprocess.run(["tar", "-tvf", path], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"tar -tvf failed for {path}: {result.stderr.strip()}")
    return _format_tar_listing(result.stdout)


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


def copy_local_file(src_path, dest_dir):
    """Copy a local file into dest_dir; return (local_path, sha256_hex)."""
    filename = os.path.basename(src_path)
    dest = os.path.join(dest_dir, filename)
    shutil.copy2(src_path, dest)
    digest = hashlib.sha256()
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return dest, digest.hexdigest()


def validate_entry(entry, source_file):
    """Validate one bundle entry; return an error string or None."""
    missing = REQUIRED_FIELDS - set(entry.keys())
    if missing:
        return f"{source_file}: missing required fields: {sorted(missing)}"
    src = entry["source-location"]
    if not isinstance(src, (str, list)) or (isinstance(src, list) and not src):
        return f"{source_file}: `source-location` must be a URL string, a non-empty list of URLs, or a local tarball filename"
    if isinstance(src, str) and is_local_source(src):
        if os.path.isabs(src) or ".." in src.replace("\\", "/").split("/"):
            return f"{source_file}: local `source-location` must not be an absolute path or contain '..'"
        if not any(src.endswith(ext) for ext in TARBALL_EXTENSIONS):
            return (
                f"{source_file}: local `source-location` must be a tarball "
                f"({', '.join(TARBALL_EXTENSIONS)})"
            )
    if not isinstance(entry.get("category"), str) or not entry["category"].strip():
        return f"{source_file}: `category` must be a non-empty string"
    subcategory = entry.get("subcategory")
    if subcategory is not None and (not isinstance(subcategory, str) or not subcategory.strip()):
        return f"{source_file}: `subcategory` must be a non-empty string when present"
    if "readme" in entry and not isinstance(entry["readme"], str):
        return f"{source_file}: `readme` must be a string"
    if "directory" in entry and not isinstance(entry["directory"], str):
        return f"{source_file}: `directory` must be a string"
    return None


def check_duplicate(models_dir, entry, source_file):
    """Return an error string if the version already exists in the summary, else None."""
    bundle = entry["bundle"]
    version = str(entry["version"])
    spath = summary_path(models_dir, bundle, entry["category"], entry.get("subcategory"))
    if os.path.exists(spath):
        summary = load_yaml(spath)
        existing = [str(v["version"]) for v in summary.get("versions", [])]
        if version in existing:
            return (
                f"{source_file}: version {version!r} of bundle {bundle!r} "
                f"already exists in {spath}"
            )
    return None


def get_inherited_readme(models_dir, entry):
    """Return readme from the most recent version in the summary, or None."""
    spath = summary_path(models_dir, entry["bundle"], entry["category"], entry.get("subcategory"))
    if not os.path.exists(spath):
        return None
    summary = load_yaml(spath)
    versions = summary.get("versions", [])
    if not versions:
        return None
    return versions[-1].get("readme")


def update_summary(models_dir, entry, sha256_info, added):
    """Append the entry to its summary file, creating it if needed."""
    bundle = entry["bundle"]
    version = str(entry["version"])
    category = entry["category"]
    subcategory = entry.get("subcategory")
    spath = summary_path(models_dir, bundle, category, subcategory)

    os.makedirs(os.path.dirname(spath), exist_ok=True)

    if os.path.exists(spath):
        summary = load_yaml(spath)
    else:
        summary = {"bundle": bundle, "category": category}
        if subcategory:
            summary["subcategory"] = subcategory
        summary["versions"] = []

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


def _write_tar_listing(tarball_path, bundle, version, artifact_dir):
    """Write a tar -tvf listing to artifact_dir; silently skip if tar fails."""
    try:
        listing = get_tar_listing(tarball_path)
    except RuntimeError as exc:
        print(f"  WARNING: could not list {tarball_path}: {exc}")
        return
    stem = f"listing_{bundle}_{version}"
    with open(os.path.join(artifact_dir, f"{stem}.txt"), "w") as f:
        f.write(listing)


def process_file(models_dir, submission_file, dry_run, artifact_dir=None):
    """
    Validate all entries in submission_file atomically, then (if not dry_run)
    inherit missing readmes, fetch/copy sources, write summaries, write the
    resolved submission YAML to artifact_dir (if given), and delete the
    submission file.  Local tarballs are also removed from the working tree.

    Returns (ok, messages, updated_summaries, local_tarballs_removed)
    local_tarballs_removed contains repo-relative paths of removed local files.
    """
    data = load_yaml(submission_file)

    if "bundles" not in data or not isinstance(data["bundles"], list):
        return False, [f"{submission_file}: must contain a top-level `bundles` list"], [], []

    entries = data["bundles"]
    if not entries:
        return False, [f"{submission_file}: `bundles` list is empty"], [], []

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
        return False, errors, [], []

    # --- write pass ---
    messages = []
    updated_summaries = []
    local_tarballs_removed = []

    if not dry_run:
        for entry in entries:
            if "readme" not in entry:
                inherited = get_inherited_readme(models_dir, entry)
                if inherited:
                    entry["readme"] = inherited
                    messages.append(f"  inherited readme for {entry['bundle']} v{entry['version']}")

        if artifact_dir:
            os.makedirs(artifact_dir, exist_ok=True)
        dl_dir = artifact_dir or os.path.join(os.path.dirname(submission_file), ".dl_tmp")
        os.makedirs(dl_dir, exist_ok=True)

        src_checksums = {}  # src string → sha256_hex
        for entry in entries:
            subdir = entry.get("directory", "").lstrip("/")
            dest_dir = os.path.join(dl_dir, subdir) if subdir else dl_dir
            os.makedirs(dest_dir, exist_ok=True)
            for src in normalize_sources(entry):
                if src in src_checksums:
                    continue
                try:
                    if is_local_source(src):
                        local_path = os.path.join(models_dir, src)
                        copied_path, chksum = copy_local_file(local_path, dest_dir)
                        src_checksums[src] = chksum
                        messages.append(f"  copied local {src} (sha256: {chksum[:12]}…)")
                        if artifact_dir:
                            _write_tar_listing(copied_path, entry["bundle"], entry["version"], artifact_dir)
                            messages.append(f"  wrote tar listing for {src}")
                    else:
                        downloaded_path, chksum = download_file(src, dest_dir)
                        src_checksums[src] = chksum
                        messages.append(f"  downloaded {src} (sha256: {chksum[:12]}…)")
                        if artifact_dir and any(src.endswith(ext) for ext in TARBALL_EXTENSIONS):
                            _write_tar_listing(downloaded_path, entry["bundle"], entry["version"], artifact_dir)
                            messages.append(f"  wrote tar listing for {os.path.basename(src)}")
                except (urllib.error.URLError, RuntimeError, OSError) as exc:
                    return False, messages + [f"  failed to process {src}: {exc}"], [], []

        added = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

        for entry in entries:
            sources = normalize_sources(entry)
            if isinstance(entry["source-location"], str):
                entry["sha256"] = src_checksums[entry["source-location"]]
            else:
                entry["sha256"] = [src_checksums[u] for u in sources]
            entry["added"] = added

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

        # Remove local tarballs from the working tree (staged as deletions by the caller)
        for entry in entries:
            for src in normalize_sources(entry):
                if is_local_source(src):
                    local_path = os.path.join(models_dir, src)
                    if os.path.exists(local_path):
                        os.remove(local_path)
                        local_tarballs_removed.append(local_path)
                        messages.append(f"  removed local tarball {local_path}")

        os.remove(submission_file)
        messages.append(f"  removed {submission_file}")
    else:
        for entry in entries:
            sources = normalize_sources(entry)
            src_display = sources[0] if len(sources) == 1 else f"{len(sources)} files"
            local = " [local]" if len(sources) == 1 and is_local_source(sources[0]) else ""
            messages.append(
                f"  OK: {entry['bundle']} v{entry['version']} ({src_display}{local})"
            )

    return True, messages, updated_summaries, local_tarballs_removed


def _git_show(ref, path):
    """Return file content at a git ref, or None if not found."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True,
    )
    return result.stdout if result.returncode == 0 else None


def _category_subcategory_from_path(models_dir, summary_file):
    rel = os.path.relpath(summary_file, models_dir).replace("\\", "/")
    parts = rel.split("/")
    if len(parts) == 2:
        return parts[0], None
    if len(parts) == 3:
        return parts[0], parts[1]
    return None, None


def process_summary_file(models_dir, summary_file, dry_run, artifact_dir=None, base_ref=None):
    """
    Handle a directly-edited summary file (append-only new versions only).
    Local source-location is not supported in directly-edited summary files.

    Returns (ok, messages, updated_summaries, local_tarballs_removed=[])
    """
    category, subcategory = _category_subcategory_from_path(models_dir, summary_file)
    if category is None:
        return False, [
            f"{summary_file}: must be under <models_dir>/<category>/[<subcategory>/]summary_<bundle>.yml"
        ], [], []

    current = load_yaml(summary_file)
    if not isinstance(current, dict) or "versions" not in current:
        return False, [f"{summary_file}: must have a top-level 'versions' list"], [], []

    bundle = current.get("bundle", "")
    expected = os.path.basename(summary_file)[len("summary_"):-len(".yml")]
    if bundle != expected:
        return False, [
            f"{summary_file}: 'bundle' field {bundle!r} does not match filename (expected {expected!r})"
        ], [], []

    if current.get("category", category) != category:
        return False, [
            f"{summary_file}: 'category' field {current['category']!r} does not match "
            f"directory ({category!r})"
        ], [], []
    if subcategory and current.get("subcategory", subcategory) != subcategory:
        return False, [
            f"{summary_file}: 'subcategory' field {current['subcategory']!r} does not match "
            f"directory ({subcategory!r})"
        ], [], []

    current_versions = current.get("versions", [])
    current_by_ver = {str(v["version"]): v for v in current_versions}

    old_versions = []
    if base_ref:
        old_text = _git_show(base_ref, summary_file)
        if old_text:
            old_data = yaml.safe_load(old_text) or {}
            old_versions = old_data.get("versions", [])
    old_by_ver = {str(v["version"]): v for v in old_versions}

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
        return False, errors, [], []

    new_entries = [v for v in current_versions if str(v["version"]) not in old_by_ver]
    if not new_entries:
        return True, [f"{summary_file}: no new versions found (nothing to do)"], [], []

    for ve in new_entries:
        src = ve.get("source-location", "")
        if isinstance(src, str) and is_local_source(src):
            errors.append(
                f"{summary_file}: local source-location is not supported in directly-edited "
                "summary files; use a submission YAML instead"
            )
        synthetic = {
            "bundle": bundle,
            "category": category,
            "version": ve.get("version", ""),
            "source-location": src,
        }
        if subcategory:
            synthetic["subcategory"] = subcategory
        for k in ("directory", "readme"):
            if k in ve:
                synthetic[k] = ve[k]
        err = validate_entry(synthetic, summary_file)
        if err:
            errors.append(err)
    if errors:
        return False, errors, [], []

    messages = []

    if dry_run:
        for ve in new_entries:
            sources = normalize_sources({"source-location": ve["source-location"]})
            src_display = sources[0] if len(sources) == 1 else f"{len(sources)} files"
            messages.append(f"  OK (new): {bundle} v{ve['version']} ({src_display})")
        return True, messages, [], []

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
                downloaded_path, chksum = download_file(url, dest_dir)
                url_checksums[url] = chksum
                messages.append(f"  downloaded {url} (sha256: {chksum[:12]}…)")
                if artifact_dir and any(url.endswith(ext) for ext in TARBALL_EXTENSIONS):
                    _write_tar_listing(downloaded_path, bundle, ve["version"], artifact_dir)
                    messages.append(f"  wrote tar listing for {os.path.basename(url)}")
            except urllib.error.URLError as exc:
                return False, messages + [f"  failed to download {url}: {exc}"], [], []

        src = ve["source-location"]
        if isinstance(src, str):
            ve["sha256"] = url_checksums[src]
        else:
            ve["sha256"] = [url_checksums[u] for u in src]
        ve["added"] = added
        messages.append(f"  filled in sha256/added for {bundle} v{ve['version']}")

    with open(summary_file, "w") as f:
        yaml.dump(current, f, default_flow_style=False, sort_keys=False)

    if artifact_dir:
        artifact_data = {
            "bundles": [
                {
                    "bundle": bundle,
                    "category": category,
                    **( {"subcategory": subcategory} if subcategory else {} ),
                    "version": str(ve["version"]),
                    "source-location": ve["source-location"],
                    "sha256": ve["sha256"],
                    "added": ve["added"],
                    **{k: ve[k] for k in ("directory", "readme") if k in ve},
                }
                for ve in new_entries
            ]
        }
        stem = f"{category}_{subcategory}_{bundle}" if subcategory else f"{category}_{bundle}"
        json_dest = os.path.join(artifact_dir, f"{stem}.json")
        with open(json_dest, "w") as f:
            json.dump(artifact_data, f, indent=2)
        messages.append(f"  wrote artifact {json_dest}")

    return True, messages, [summary_file], []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("submission_files", nargs="+", help="Submission or summary YAML files to process")
    parser.add_argument("--models-dir", default="production_bundles")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not write")
    parser.add_argument("--artifact-dir", default=None, help="Write resolved YAMLs/JSON/listings here")
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
    all_local_tarballs = []
    report_lines = []

    for sfile in args.submission_files:
        if os.path.basename(sfile).startswith("summary_"):
            ok, messages, updated, _ = process_summary_file(
                args.models_dir, sfile, args.dry_run, args.artifact_dir, args.base_ref
            )
        else:
            ok, messages, updated, local_removed = process_file(
                args.models_dir, sfile, args.dry_run, args.artifact_dir
            )
            all_local_tarballs.extend(local_removed)
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
            "### FCC Production Bundles — validation passed ✅"
            if all_ok
            else "### FCC Production Bundles — validation failed ❌"
        )
        note = (
            "_On merge: summaries will be updated and submission files removed._"
            if all_ok and args.dry_run
            else ""
        )
        print("\n".join([header, ""] + report_lines + (["", note] if note else [])))

    if not all_ok:
        sys.exit(1)

    gho = os.environ.get("GITHUB_OUTPUT")
    if gho:
        with open(gho, "a") as f:
            if all_updated_summaries:
                f.write(f"updated_summaries={' '.join(all_updated_summaries)}\n")
            if all_local_tarballs:
                f.write(f"local_tarballs={' '.join(all_local_tarballs)}\n")


if __name__ == "__main__":
    main()
