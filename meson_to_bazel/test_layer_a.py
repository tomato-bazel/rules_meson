#!/usr/bin/env python3
"""Tests for the Layer-A down-projection + the decomposition-validation gate.

    python3 test_layer_a.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import emit_kythe  # noqa: E402
import mozbuild_frontend  # noqa: E402
import validate_partition  # noqa: E402


def main():
    objects = json.load(open(os.path.join(HERE, "testdata/firefox_like.objects.json")))
    graph = mozbuild_frontend.convert(objects, "firefox")

    # Layer-A: one CompilationUnit per (compile target, source); VName shares the
    # corpus + component + path the gate keys on.
    cus = emit_kythe.compilation_units(graph, root="")
    assert len(cus) == 4, "expected 4 TUs (2 dombindings, 1 xpcom, 1 firefox), got %d" % len(cus)
    bu = [c for c in cus if c["v_name"]["path"] == "dom/bindings/BindingUtils.cpp"][0]
    assert bu["v_name"]["corpus"] == "firefox"
    assert bu["v_name"]["root"] == "dom/bindings"          # component carried in VName
    assert bu["v_name"]["language"] == "c++"
    assert "-DMOZILLA_INTERNAL_API" in bu["argument"]
    assert "-Idom/bindings" in bu["argument"]
    assert bu["source_file"] == ["dom/bindings/BindingUtils.cpp"]

    # Gate: a symbol graph that backs dom/bindings->xpcom but not the
    # firefox->dombindings build dep, and reveals a hidden browser/app->xpcom ref.
    edges = [
        {"from": "dom/bindings/BindingUtils.cpp", "to": "xpcom/base/nsCOMPtr.cpp"},
        {"from": "browser/app/nsBrowserApp.cpp", "to": "xpcom/base/nsCOMPtr.cpp"},
    ]
    over_broad, hidden = validate_partition.analyze(graph, edges)
    assert ("browser/app", "dom/bindings") in over_broad, over_broad
    assert ("browser/app", "xpcom/base") in hidden, hidden
    assert ("dom/bindings", "xpcom/base") not in over_broad  # symbol-backed -> clean

    # A clean cut: symbol-back every build dep, no extra crossings.
    clean_edges = [
        {"from": "dom/bindings/BindingUtils.cpp", "to": "xpcom/base/nsCOMPtr.cpp"},
        {"from": "browser/app/nsBrowserApp.cpp", "to": "dom/bindings/BindingUtils.cpp"},
    ]
    ob2, hd2 = validate_partition.analyze(graph, clean_edges)
    assert ob2 == [] and hd2 == [], (ob2, hd2)

    print("PASS layer-A: CompilationUnit VName/args; gate flags over-broad + hidden; clean cut clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
