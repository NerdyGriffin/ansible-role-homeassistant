#!/usr/bin/env python3
"""Extract members from a Home Assistant backup archive.

A Home Assistant backup is a plain outer tar holding ``homeassistant.tar.gz``.
When the backup is protected, that inner archive is a SecureTar stream and the
encryption password is needed to read it.

The password is read from STDIN, never from argv or a file, so it does not
appear in a process listing or on disk.
"""

from __future__ import annotations

import argparse
import os
import sys
import tarfile
import tempfile
from pathlib import Path

from securetar import SecureTarFile

INNER_ARCHIVE = "homeassistant.tar.gz"
COPY_CHUNK = 8 << 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, help="path to the outer .tar")
    parser.add_argument("--outdir", required=True, help="where to write members")
    parser.add_argument(
        "--want",
        action="append",
        default=[],
        help="substring of an inner member path; repeatable",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="list the inner members and exit",
    )
    return parser.parse_args()


def stage_inner_archive(backup: str, outdir: str) -> str:
    """Copy the encrypted inner archive out of the plain outer tar."""
    with tarfile.open(backup, "r:") as outer:
        try:
            source = outer.extractfile(INNER_ARCHIVE)
        except KeyError:
            source = None
        if source is None:
            raise SystemExit(
                f"{backup}: no {INNER_ARCHIVE} member "
                f"(found: {outer.getnames()[:10]})"
            )
        with tempfile.NamedTemporaryFile(
            dir=outdir, suffix=".inner", delete=False
        ) as staged:
            while chunk := source.read(COPY_CHUNK):
                staged.write(chunk)
            return staged.name


def main() -> int:
    args = parse_args()
    if not args.want and not args.list_only:
        print("ERROR: pass --want or --list-only", file=sys.stderr)
        return 2

    password = sys.stdin.readline().rstrip("\n") or None
    os.makedirs(args.outdir, exist_ok=True)
    inner_path = stage_inner_archive(args.backup, args.outdir)

    archive = SecureTarFile(Path(inner_path), password=password, gzip=True)
    if password and not archive.validate_password():
        os.unlink(inner_path)
        print("ERROR: the backup password was rejected", file=sys.stderr)
        return 5

    extracted: list[tuple[str, str, int]] = []
    try:
        with archive.open() as inner:
            for member in inner:
                if args.list_only:
                    print(member.name)
                    continue
                if not member.isfile():
                    continue
                if not any(want in member.name for want in args.want):
                    continue
                destination = os.path.join(args.outdir, os.path.basename(member.name))
                source = inner.extractfile(member)
                with open(destination, "wb") as sink:
                    while chunk := source.read(COPY_CHUNK):
                        sink.write(chunk)
                extracted.append(
                    (member.name, destination, os.path.getsize(destination))
                )
    finally:
        archive.close()
        os.unlink(inner_path)

    for name, destination, size in extracted:
        print(f"EXTRACTED {name} -> {destination} ({size} bytes)")
    if not extracted and not args.list_only:
        print("ERROR: no inner member matched --want", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
