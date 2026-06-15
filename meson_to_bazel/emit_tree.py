#!/usr/bin/env python3
"""Tree emit: build-IR BuildGraph -> one idiomatic BUILD.bazel per package.

emit_bazel.py renders the whole graph into a single BUILD (fine for one
component / a meson project). For a *whole source tree* — the Firefox case — the
idiomatic output is one BUILD per directory/package, with cross-package
dependencies expressed as proper `//pkg:target` labels rather than `:target`.

This is the function a repository rule calls at fetch time: given the BuildGraph
(produced by the mozbuild frontend over the http_archive'd source), it writes a
BUILD.bazel into every package directory, so `@firefox//dom/bindings:dombindings`
resolves idiomatically.

`emit_tree(graph)` returns {package_dir: build_text}.

    emit_tree.py <build_graph.json> --out <dir>   # writes <dir>/<pkg>/BUILD.bazel
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import emit_bazel  # noqa: E402  (reuse _strlist / _genrule_cmd)

_PUBLIC = ["//visibility:public"]


def _label(dep_name, dep_comp, here):
    """Cross-package -> //pkg:target ; same-package -> :target."""
    return ":" + dep_name if dep_comp == here else "//{}:{}".format(dep_comp, dep_name)


def _pkg_rel(path, comp):
    """Tree-relative path -> package-relative within `comp` (idiomatic in a BUILD)."""
    if comp and path == comp:
        return "."
    prefix = comp + "/"
    return path[len(prefix):] if comp and path.startswith(prefix) else path


def _relativize(t, comp):
    """Return a copy of target `t` with all its own paths made package-relative."""
    t = dict(t)
    if "codegen" in t:
        cg = dict(t["codegen"])
        cg["outputs"] = [_pkg_rel(o, comp) for o in cg.get("outputs", [])]
        cg["inputs"] = [_pkg_rel(i, comp) for i in cg.get("inputs", [])]
        t["codegen"] = cg
    for key in ("sources", "headers", "includes"):
        if key in t:
            t[key] = [_pkg_rel(p, comp) for p in t[key]]
    return t


def emit_tree(graph):
    targets = graph.get("targets", [])
    comp_of = {t["name"]: t.get("component", "") for t in targets}
    gen_outputs = {
        t["name"]: t.get("codegen", {}).get("outputs", [])
        for t in targets if t["kind"] == "TARGET_KIND_GENERATED"
    }

    by_comp = {}
    for t in targets:
        by_comp.setdefault(t.get("component", ""), []).append(t)

    out = {}
    for comp, ts in sorted(by_comp.items()):
        blocks = emit_bazel._load_lines(emit_bazel._loads_for(ts))
        if blocks:
            blocks.append("")
        for t in ts:
            if t["kind"] == "TARGET_KIND_GENERATED":
                # Public: a codegen output may be consumed from another package.
                blocks.append(emit_bazel._emit_generated(_relativize(t, comp), _PUBLIC))
                continue
            # Resolve deps: generated sources fold in (package-relative if local,
            # //pkg:out if cross-package); library deps become //pkg:lib or :lib.
            rel = _relativize(t, comp)
            srcs = list(rel.get("sources", []))
            deps = []
            for d in t.get("deps", []):
                dc = comp_of.get(d, "")
                if d in gen_outputs:
                    srcs += [_pkg_rel(o, comp) if dc == comp else "//{}:{}".format(dc, _pkg_rel(o, dc))
                             for o in gen_outputs[d]]
                else:
                    deps.append(_label(d, dc, comp))
            rel["srcs_resolved"] = list(dict.fromkeys(srcs))
            rel["deps_resolved"] = list(dict.fromkeys(deps))
            # Libraries are depended on across packages -> public; binaries are
            # leaves -> default (private) visibility.
            if t["kind"] == "TARGET_KIND_LIBRARY":
                blocks.append(emit_bazel._emit_cc(rel, "cc_library", _PUBLIC))
            else:
                blocks.append(emit_bazel._emit_cc(rel, "cc_binary"))
        out[comp] = "\n".join(blocks)
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("build_graph")
    ap.add_argument("--out", help="write <out>/<pkg>/BUILD.bazel; else print a manifest")
    args = ap.parse_args(argv)
    tree = emit_tree(json.load(open(args.build_graph)))
    if args.out:
        for comp, text in tree.items():
            d = os.path.join(args.out, comp)
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, "BUILD.bazel"), "w").write(text)
        print("wrote {} BUILD.bazel files under {}".format(len(tree), args.out))
    else:
        for comp, text in sorted(tree.items()):
            print("=== //{}/BUILD.bazel ===".format(comp))
            print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
