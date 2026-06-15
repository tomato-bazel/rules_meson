#!/usr/bin/env python3
"""Cargo frontend for the build-IR (Layer B) — the Rust path.

Reads `cargo metadata --format-version 1 --no-deps` JSON and emits a
build_ir.v1 BuildGraph. The third frontend (after meson + mozbuild), confirming
the IR is build-system-agnostic: a Rust/Cargo workspace (e.g. Servo) comes up
through the same pipeline -> idiomatic Bazel (rules_rust rust_library /
rust_binary).

Maps each workspace package's targets:
  * kind 'lib' / 'rlib' -> LIBRARY (rust)
  * kind 'bin'          -> EXECUTABLE (rust)
sources = the crate root (`src_path`); `edition` carried through; deps = the
package's **path** dependencies (crate names). External (registry) deps would
resolve through crate_universe (`@crates//:name`) — left for the crate-universe
pass, not emitted for a workspace-local graph.

Usage:
    cargo metadata --format-version 1 --no-deps > meta.json
    cargo_frontend.py meta.json [--corpus servo] > build_graph.json
"""
import argparse
import json
import os
import sys


def _rel(path, root):
    return os.path.relpath(path, root) if (root and os.path.isabs(path)) else path


def convert(metadata, corpus):
    root = metadata.get("workspace_root", "")
    members = set(metadata.get("workspace_members", []))
    targets = []
    for pkg in metadata.get("packages", []):
        if members and pkg["id"] not in members:
            continue  # skip non-workspace (registry) packages
        pkg_dir = os.path.dirname(_rel(pkg["manifest_path"], root))
        deps = sorted({d["name"] for d in pkg.get("dependencies", []) if d.get("path")})
        for t in pkg.get("targets", []):
            kinds = t.get("kind", [])
            if "lib" in kinds or "rlib" in kinds:
                kind = "TARGET_KIND_LIBRARY"
            elif "bin" in kinds:
                kind = "TARGET_KIND_EXECUTABLE"
            else:
                continue  # tests/examples/build-scripts not modeled here
            tgt = {
                "name": t["name"],
                "kind": kind,
                "language": "LANGUAGE_RUST",
                "component": pkg_dir,
                "sources": [_rel(t["src_path"], root)],
                "edition": t.get("edition") or pkg.get("edition") or "2021",
            }
            if deps:
                tgt["deps"] = deps
            targets.append(tgt)
    return {"corpus": corpus, "root": root, "targets": targets}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("metadata_json", help="`cargo metadata --format-version 1` output")
    ap.add_argument("--corpus", default="")
    args = ap.parse_args(argv)
    graph = convert(json.load(open(args.metadata_json)), args.corpus)
    json.dump(graph, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main(sys.argv[1:])
