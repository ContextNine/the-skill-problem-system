#!/usr/bin/env python3

import argparse
import gzip
import hashlib
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("dist-release"))
    args = parser.parse_args()

    release = json.loads(Path("release.json").read_text(encoding="utf-8"))
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise SystemExit("source commit must be a full SHA")

    version = release["version"]
    basename = f"the-skill-problem-system-{version}"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    archive = args.output_dir / f"{basename}.tar.gz"
    tar = subprocess.check_output(["git", "archive", "--format=tar", "HEAD"])
    with archive.open("wb") as destination:
        with gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0) as compressed:
            compressed.write(tar)

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (args.output_dir / f"{archive.name}.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    (args.output_dir / f"{basename}.release.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repository": "ContextNine/the-skill-problem-system",
                "version": version,
                "tag": release["tag"],
                "source_commit": commit,
                "artifact": archive.name,
                "sha256": digest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
