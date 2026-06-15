#!/usr/bin/env python3
"""Golden test for the Cargo frontend (the Rust path)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cargo_frontend  # noqa: E402
import emit_bazel  # noqa: E402
import emit_tree  # noqa: E402


def main():
    td = os.path.join(HERE, "testdata")
    meta = json.load(open(os.path.join(td, "cargo_metadata.json")))
    graph = cargo_frontend.convert(meta, "cargodemo")

    got = emit_bazel.emit(graph)
    golden = open(os.path.join(td, "cargo.golden.BUILD")).read()
    if got != golden:
        sys.stderr.write("cargo golden MISMATCH:\n" + got)
        return 1

    # Rust path emits rules_rust rules with editions; app depends on greet.
    assert 'load("@rules_rust//rust:defs.bzl"' in got
    assert "rust_library(" in got and "rust_binary(" in got
    assert 'edition = "2021"' in got
    assert '":greet"' in got and "cc_library" not in got

    # Tree emit: per-package, cross-package label dep, public lib, package-relative src.
    tree = emit_tree.emit_tree(graph)
    assert set(tree) == {"greet", "app"}, set(tree)
    assert '"//greet:greet"' in tree["app"]
    assert "//visibility:public" in tree["greet"]
    assert '"src/lib.rs"' in tree["greet"] and "greet/src/lib.rs" not in tree["greet"]

    print("PASS cargo: rust_library/rust_binary + edition + cross-package //greet:greet (Rust frontend)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
