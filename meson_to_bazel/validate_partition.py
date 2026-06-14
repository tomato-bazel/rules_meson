#!/usr/bin/env python3
"""Decomposition-validation gate (build-ir-seams.md §5).

A component partition derived from *build dependencies* is only a claim. Given
the build-IR BuildGraph (whose targets carry `component` assignments) and a
*symbol-reference* edge list (path -> path, as an indexer emits from the Kythe
graph over the actual source), this reports the two ways a cut can be wrong:

  * OVER-BROAD  — a build dependency crosses a component boundary but NO symbol
                  reference backs it: a candidate edge to drop / split.
  * HIDDEN      — a symbol reference crosses a component boundary but NO build
                  dependency declares it: a hidden coupling that breaks the cut.

Both sides are keyed on the same file paths — which are exactly the VName paths
of the Layer-A down-projection (emit_kythe.py). That shared identity is the
whole reason the build and code-analysis layers align on Kythe rather than
running parallel models.

Usage:
    validate_partition.py <build_graph.json> <symbol_edges.json>
        symbol_edges.json: [{"from": "<path>", "to": "<path>"}, ...]
Exit status: 0 if the cut is clean, 1 if any finding.
"""
import json
import sys


def _component_indexes(graph):
    comp_of_target, comp_of_path = {}, {}
    for t in graph.get("targets", []):
        comp = t.get("component", "")
        comp_of_target[t["name"]] = comp
        for s in t.get("sources", []):
            comp_of_path[s] = comp
    return comp_of_target, comp_of_path


def analyze(graph, symbol_edges):
    comp_of_target, comp_of_path = _component_indexes(graph)

    # Cross-component edges declared by build deps: {(compA, compB)}.
    build_cross = set()
    for t in graph.get("targets", []):
        a = comp_of_target.get(t["name"], "")
        for d in t.get("deps", []):
            b = comp_of_target.get(d)
            if b is not None and a != b:
                build_cross.add((a, b))

    # Cross-component edges observed in the symbol graph.
    symbol_cross = set()
    for e in symbol_edges:
        a = comp_of_path.get(e["from"])
        b = comp_of_path.get(e["to"])
        if a is not None and b is not None and a != b:
            symbol_cross.add((a, b))

    over_broad = sorted(build_cross - symbol_cross)
    hidden = sorted(symbol_cross - build_cross)
    return over_broad, hidden


def main(argv):
    graph = json.load(open(argv[0]))
    edges = json.load(open(argv[1]))
    over_broad, hidden = analyze(graph, edges)

    for a, b in over_broad:
        print("OVER-BROAD  build dep {!r} -> {!r} has no symbol references".format(a, b))
    for a, b in hidden:
        print("HIDDEN      symbol refs {!r} -> {!r} with no build dependency".format(a, b))
    if not over_broad and not hidden:
        print("clean: every cross-component build dep is symbol-backed, and every "
              "cross-component symbol ref is declared")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
