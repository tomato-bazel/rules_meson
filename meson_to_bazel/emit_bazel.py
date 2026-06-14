#!/usr/bin/env python3
"""Bazel backend for the build-IR (Layer B).

Consumes a build_ir.v1 BuildGraph (proto3-JSON, as emitted by any frontend —
meson today, mozbuild next) and emits a BUILD.bazel:

    TARGET_KIND_GENERATED  -> genrule
    TARGET_KIND_LIBRARY    -> cc_library
    TARGET_KIND_EXECUTABLE -> cc_binary

This backend is frontend-agnostic on purpose: it is the shared emit half of the
build-IR, so the meson and moz.build frontends produce identical Bazel from the
same IR. See polyglot docs build-ir-seams.md.

Usage:
    emit_bazel.py <build_graph.json> > BUILD.bazel
"""
import json
import shlex
import sys


def _genrule_cmd(command, n_outputs):
    """Turn a neutral IR codegen argv into a genrule `cmd` string.

    Maps the neutral {OUTPUT}/{INPUT} tokens to Bazel make-vars ($@ for a single
    output, else $(OUTS); $(SRCS) for inputs), and unwraps the common
    `sh -c <script>` form since genrule already runs its cmd through bash.
    """
    out_var = "$@" if n_outputs == 1 else "$(OUTS)"

    def sub(s):
        return s.replace("{OUTPUT}", out_var).replace("{INPUT}", "$(SRCS)")

    if len(command) >= 3 and command[0].rsplit("/", 1)[-1] in ("sh", "bash") and command[1] == "-c":
        return sub(command[2])
    # Emit make-var placeholders unquoted (they must expand + word-split);
    # shell-quote every other argument.
    parts = []
    for a in command:
        if a == "{OUTPUT}":
            parts.append(out_var)
        elif a == "{INPUT}":
            parts.append("$(SRCS)")
        else:
            parts.append(shlex.quote(sub(a)))
    return " ".join(parts)


def _strlist(name, values, indent="    "):
    if not values:
        return ""
    items = "".join('{i}    "{v}",\n'.format(i=indent, v=v) for v in values)
    return "{i}{name} = [\n{items}{i}],\n".format(i=indent, name=name, items=items)


def _emit_generated(t, visibility=None):
    cg = t.get("codegen", {})
    outputs = cg.get("outputs", [])
    cmd = _genrule_cmd(cg.get("command", []), len(outputs))
    out = "".join(
        '''    name = "{name}",
{outs}{srcs}    cmd = {cmd},
{vis}'''.format(
            name=t["name"],
            outs=_strlist("outs", outputs),
            srcs=_strlist("srcs", cg.get("inputs", [])),
            cmd=json.dumps(cmd),
            vis=_strlist("visibility", visibility),
        )
    )
    return "genrule(\n{}\n)\n".format(out.rstrip("\n"))


def _emit_cc(t, rule, visibility=None):
    # Deps to GENERATED targets become srcs entries (their outputs); deps to
    # libraries become Bazel label deps. The frontend records dep names; the
    # caller resolves kinds via `gen_names`.
    return "{rule}(\n{body}\n)\n".format(
        rule=rule,
        body="".join(
            [
                '    name = "{}",\n'.format(t["name"]),
                _strlist("srcs", t.get("srcs_resolved", t.get("sources", []))),
                _strlist("hdrs", t.get("headers", [])),
                _strlist("includes", t.get("includes", [])),
                _strlist("defines", t.get("defines", [])),
                _strlist("copts", t.get("copts", [])),
                _strlist("deps", t.get("deps_resolved", [])),
                _strlist("visibility", visibility),
            ]
        ).rstrip("\n"),
    )


def emit(graph):
    targets = graph.get("targets", [])
    gen_outputs = {
        t["name"]: t.get("codegen", {}).get("outputs", [])
        for t in targets
        if t["kind"] == "TARGET_KIND_GENERATED"
    }

    # Resolve dep names into Bazel-shaped srcs/deps per consumer.
    for t in targets:
        if t["kind"] in ("TARGET_KIND_LIBRARY", "TARGET_KIND_EXECUTABLE"):
            srcs = list(t.get("sources", []))
            deps = []
            for d in t.get("deps", []):
                if d in gen_outputs:           # generated source: add its outputs to srcs
                    srcs += gen_outputs[d]
                else:                           # library: a label dep
                    deps.append(":" + d)
            # A generated .cpp can be both a declared source and a folded codegen
            # output; order-preserving dedup keeps one.
            t["srcs_resolved"] = list(dict.fromkeys(srcs))
            t["deps_resolved"] = list(dict.fromkeys(deps))

    blocks = ['load("@rules_cc//cc:defs.bzl", "cc_binary", "cc_library")', ""]
    for t in targets:
        if t["kind"] == "TARGET_KIND_GENERATED":
            blocks.append(_emit_generated(t))
        elif t["kind"] == "TARGET_KIND_LIBRARY":
            blocks.append(_emit_cc(t, "cc_library"))
        elif t["kind"] == "TARGET_KIND_EXECUTABLE":
            blocks.append(_emit_cc(t, "cc_binary"))
    return "\n".join(blocks)


def main(argv):
    graph = json.load(open(argv[0]))
    sys.stdout.write(emit(graph))


if __name__ == "__main__":
    main(sys.argv[1:])
