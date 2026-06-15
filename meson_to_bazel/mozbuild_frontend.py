#!/usr/bin/env python3
"""mozbuild frontend for the build-IR (Layer B) — the Firefox path.

The second frontend into build_ir.proto (the first is meson_frontend.py). It
consumes the object stream Mozilla's `mozbuild.frontend.emitter.TreeMetadataEmitter`
produces — serialized to JSON by a thin mozbuild `BuildBackend` (the mozbuild
analogue of meson's `introspect --targets`, ~30 lines: iterate the emitter
objects, `json.dump` the subset of fields below). It then emits the SAME
build_ir.v1.BuildGraph that emit_bazel.py turns into Bazel — proving the IR and
backend are frontend-agnostic.

Two real differences from the meson shape, handled here:

  1. **Ungrouped, per-context objects.** mozbuild emits `Sources`, `Defines`,
     `LocalInclude`, and the `StaticLibrary`/`Program` as *separate* objects
     tagged with their source directory (`context`). The frontend groups by
     context to assemble each target — work meson's pre-grouped `target_sources`
     did for us.
  2. **Generated-source consume edge is recoverable.** A library whose sources
     include a `GeneratedFile`'s output gets a dep on that codegen target — the
     produces→consumes edge meson's `introspect --targets` could not surface.

Input JSON: a list of objects, each `{"type": <mozbuild class>, "context": <dir>,
...}`. Supported types: GeneratedFile, Sources, UnifiedSources, Defines,
LocalInclude, StaticLibrary, SharedLibrary, Library, RustLibrary, Program,
SimpleProgram. `USE_LIBS` is carried on the library/program object as `use_libs`.

Usage:
    mozbuild_frontend.py <objects.json> [--corpus firefox] > build_graph.json
"""
import argparse
import json
import os
import sys

_LIB_TYPES = ("StaticLibrary", "SharedLibrary", "Library", "RustLibrary")
_EXE_TYPES = ("Program", "SimpleProgram")

# Generator script (basename) -> neutral codegen kind. Mozilla's WebIDL bindings
# come from dom/bindings/Codegen.py; XPIDL / IPDL have their own generators. A
# kind maps to a first-class Bazel rule in the emit backend (else a genrule).
_CODEGEN_KINDS = {
    "Codegen.py": "webidl",
    "xpidl.py": "xpidl",
    "ipdl.py": "ipdl",
}


def _codegen_kind(script):
    return _CODEGEN_KINDS.get(os.path.basename(script or ""), "")


def _ctx_rel(context, f):
    """mozbuild source paths are context(dir)-relative unless absolute (a
    `/topsrcdir`-rooted path); normalize to a repo-relative path."""
    if f.startswith("/"):
        return f.lstrip("/")
    return os.path.normpath(os.path.join(context, f)) if context else f


def _language(name):
    ext = os.path.splitext(name)[1].lower()
    if ext in (".cc", ".cpp", ".cxx", ".mm"):
        return "LANGUAGE_CXX"
    if ext == ".c":
        return "LANGUAGE_C"
    if ext == ".rs":
        return "LANGUAGE_RUST"
    return "LANGUAGE_UNSPECIFIED"


def convert(objects, corpus):
    # Pass 1: codegen targets + an index of generated output -> codegen name.
    gen_targets, gen_output_owner = [], {}
    for o in objects:
        if o["type"] == "GeneratedFile":
            outs = [_ctx_rel(o.get("context", ""), f) for f in o.get("outputs", [])]
            ins = [_ctx_rel(o.get("context", ""), f) for f in o.get("inputs", [])]
            # The emitter records a script + method; the runner invocation is
            # `python <script> <method> {OUTPUT} {INPUT}` (neutral placeholders).
            cmd = ["python", o["script"]]
            if o.get("method"):
                cmd.append(o["method"])
            cmd += ["{OUTPUT}", "{INPUT}"]
            gen_targets.append(
                {
                    "name": o["name"],
                    "kind": "TARGET_KIND_GENERATED",
                    "component": o.get("context", ""),
                    "codegen": {
                        "command": cmd, "inputs": ins, "outputs": outs,
                        "kind": _codegen_kind(o.get("script", "")),
                    },
                }
            )
            for out in outs:
                gen_output_owner[out] = o["name"]

    # Pass 2: group the per-context Sources/Defines/LocalInclude onto each
    # library/program defined in the same context.
    by_ctx = {}
    for o in objects:
        by_ctx.setdefault(o.get("context", ""), []).append(o)

    targets = list(gen_targets)
    for o in objects:
        if o["type"] not in _LIB_TYPES + _EXE_TYPES:
            continue
        ctx = o.get("context", "")
        siblings = by_ctx.get(ctx, [])
        sources, includes, defines = [], [], []
        for s in siblings:
            if s["type"] in ("Sources", "UnifiedSources"):
                sources += [_ctx_rel(ctx, f) for f in s.get("files", [])]
            elif s["type"] == "Defines":
                defines += list(s.get("defines", {}).keys())
            elif s["type"] == "LocalInclude":
                includes.append(s["path"].lstrip("/"))

        deps = list(o.get("use_libs", []))
        # produces->consumes: a source that is a GeneratedFile output -> dep on
        # the codegen target (emit_bazel folds its outputs into srcs).
        for src in sources:
            owner = gen_output_owner.get(src)
            if owner and owner not in deps:
                deps.append(owner)

        kind = "TARGET_KIND_LIBRARY" if o["type"] in _LIB_TYPES else "TARGET_KIND_EXECUTABLE"
        lang = next((_language(s) for s in sources if _language(s) != "LANGUAGE_UNSPECIFIED"),
                    "LANGUAGE_UNSPECIFIED")
        t = {"name": o["name"], "kind": kind, "language": lang, "component": ctx}
        if sources:
            t["sources"] = sources
        if sorted(set(includes)):
            t["includes"] = sorted(set(includes))
        if sorted(set(defines)):
            t["defines"] = sorted(set(defines))
        if deps:
            t["deps"] = sorted(set(deps))
        targets.append(t)

    return {"corpus": corpus, "root": "", "targets": targets}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("objects_json")
    ap.add_argument("--corpus", default="firefox")
    args = ap.parse_args(argv)
    objects = json.load(open(args.objects_json))
    json.dump(convert(objects, args.corpus), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main(sys.argv[1:])
