#!/usr/bin/env python3
"""Test the whole-tree per-package BUILD emit (emit_tree)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import emit_tree  # noqa: E402
import mozbuild_frontend  # noqa: E402


def main():
    objects = json.load(open(os.path.join(HERE, "testdata/firefox_like.objects.json")))
    tree = emit_tree.emit_tree(mozbuild_frontend.convert(objects, "firefox"))

    assert set(tree) == {"xpcom/base", "dom/bindings", "browser/app"}, set(tree)
    dom = tree["dom/bindings"]
    # package-relative own paths
    assert '"BindingUtils.cpp"' in dom and "dom/bindings/BindingUtils.cpp" not in dom
    assert '"FooBinding.cpp"' in dom and '"FooBinding.h"' in dom
    assert 'includes = [\n        ".",' in dom
    # cross-package dependency as a label, not a bare :target
    assert '"//xpcom/base:xpcom"' in dom
    assert '"//dom/bindings:dombindings"' in tree["browser/app"]
    assert '"nsBrowserApp.cpp"' in tree["browser/app"]
    # WebIDL codegen is a first-class webidl_library (not a genrule), loaded
    # from rules_firefox, colocated with its cc_library consumer.
    assert "webidl_library(" in dom and "cc_library" in dom
    assert 'load("@rules_firefox//firefox:defs.bzl", "webidl_library")' in dom
    assert 'srcs = [\n        "Foo.webidl",' in dom  # package-relative IDL src
    # cross-package consumability: libraries + codegen are public
    assert 'visibility = [\n        "//visibility:public",' in dom, "dombindings/genrule need visibility"
    assert "//visibility:public" in tree["xpcom/base"], "xpcom (cross-package dep) needs visibility"
    print("PASS tree: per-package BUILD, package-relative srcs, cross-package //pkg:target deps + visibility")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
