#!/usr/bin/env python3
"""Layer-A down-projection: build-IR BuildGraph -> Kythe CompilationUnits.

This is the seam to the code-analysis world (see polyglot docs build-ir-seams.md
§2-4). The build-IR (Layer B) carries the target/dep/codegen *structure*; this
projects each compile target down to the per-translation-unit Kythe
`CompilationUnit`s (analysis.proto) + `VName`s (storage.proto) that an indexer
consumes. The SAME `VName` basis (corpus + path) is what later lets the source
symbol-reference graph be diffed against the build-dependency partition to
validate a decomposition.

Emits, per (compile target, source file), a CompilationUnit as proto3-JSON:
  v_name           — the unit's identity (corpus / root=component / path / language)
  required_input[] — source + headers, each VName + content digest (kzip packs these)
  argument[]       — the reconstructed compiler invocation
  source_file[]    — the TU's source

Digests are the SHA-256 of file content when the file is present on disk
(relative to --root); absent (e.g. synthetic fixtures, or sources that are
codegen outputs not yet generated) they are left "" — the kzip step fills them
from the real tree.

Usage:
    emit_kythe.py <build_graph.json> [--root DIR] > compilation_units.json
"""
import argparse
import hashlib
import json
import os
import sys

_LANG_ARG = {"LANGUAGE_C": "cc", "LANGUAGE_CXX": "c++", "LANGUAGE_RUST": "rustc"}
_KYTHE_LANG = {"LANGUAGE_C": "c", "LANGUAGE_CXX": "c++", "LANGUAGE_RUST": "rust"}


def _digest(path, root):
    if root:
        full = os.path.join(root, path)
        if os.path.isfile(full):
            return hashlib.sha256(open(full, "rb").read()).hexdigest()
    return ""


def _vname(corpus, component, path, language):
    v = {"corpus": corpus, "path": path}
    if component:
        v["root"] = component
    if language:
        v["language"] = language
    return v


def _required_input(corpus, component, path, language, root):
    return {
        "v_name": _vname(corpus, component, path, language),
        "info": {"path": path, "digest": _digest(path, root)},
    }


def compilation_units(graph, root):
    corpus = graph.get("corpus", "")
    units = []
    for t in graph.get("targets", []):
        if t["kind"] not in ("TARGET_KIND_LIBRARY", "TARGET_KIND_EXECUTABLE"):
            continue
        lang = t.get("language", "LANGUAGE_UNSPECIFIED")
        klang = _KYTHE_LANG.get(lang, "")
        driver = _LANG_ARG.get(lang, "cc")
        flags = ["-I" + i for i in t.get("includes", [])]
        flags += ["-D" + d for d in t.get("defines", [])]
        flags += list(t.get("copts", []))
        component = t.get("component", "")

        for src in t.get("sources", []):
            argument = [driver] + flags + ["-c", src]
            required = [_required_input(corpus, component, src, klang, root)]
            required += [
                _required_input(corpus, component, h, klang, root)
                for h in t.get("headers", [])
            ]
            units.append(
                {
                    "v_name": _vname(corpus, component, src, klang),
                    "required_input": required,
                    "argument": argument,
                    "source_file": [src],
                    "working_directory": root or "/",
                    "output_key": "{}/{}.o".format(t["name"], os.path.basename(src)),
                }
            )
    return units


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("build_graph")
    ap.add_argument("--root", default="", help="source root for content digests")
    args = ap.parse_args(argv)
    graph = json.load(open(args.build_graph))
    json.dump(compilation_units(graph, args.root), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main(sys.argv[1:])
