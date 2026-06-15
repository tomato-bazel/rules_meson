# meson_to_bazel — the build-IR slice

The first concrete slice of the build-translation stack described in polyglot's
`docs/src/build-ir-seams.md`. It realizes **Layer B** (the build-target IR) with
a meson frontend and a Bazel backend:

```
meson introspect --targets   ──frontend──▶   build_ir.v1.BuildGraph   ──backend──▶   BUILD.bazel
   (meson_frontend.py)                       (build_ir.proto)                        (emit_bazel.py)
```

- **`build_ir.proto`** — the shared, frontend-agnostic schema. The thing that
  moves into a shared `build-ir` module (next to a `translator-core` harness
  shared with `rules_ci_ir`) once the **mozbuild** frontend lands. This is the
  consolidation point: moz.build becomes a *second frontend* into this IR, not a
  parallel build IR.
- **`meson_frontend.py`** — `meson introspect --targets` JSON → `BuildGraph`.
- **`emit_bazel.py`** — `BuildGraph` → `cc_library` / `cc_binary` / `genrule`.
  Frontend-agnostic, so meson and moz.build emit identical Bazel from one IR.

## Why this exists (vs. just using compile_commands.json)

A flat `compile_commands.json` (which `meson_configure` already captures, and
which is one structuring step from a Kythe `CompilationUnit`) is **per-TU and
lossy**. This slice recovers the structure it drops — demonstrated on the
checked-in fixture (a `library` + `executable` + `custom_target`):

- **target grouping** — `core.c` → `cc_library(core)`, `main.c` → `cc_binary(app)`;
- **dependency edges** — `app → :core`, recovered from the **link line**
  (meson's `introspect` leaves `depends` empty);
- **codegen** — the `custom_target` → a `genrule` (with meson's `@OUTPUT@`
  mapped to `$@` and the `sh -c` form unwrapped).

`build_ir.proto`'s `corpus` + `Target.name` are the **Kythe `VName` basis**: each
target down-projects to Layer-A `CompilationUnit`s, which is how polyglot's
`Lir → Entry` symbol graph can later **validate the decomposition** (§5 of the
seams doc).

## Run

```sh
python3 test_roundtrip.py        # golden test, no meson/bazel needed

# against a live meson build dir:
meson introspect <builddir> --targets > targets.json
python3 meson_frontend.py targets.json --root <srcroot> --corpus myproj > graph.json
python3 emit_bazel.py graph.json > BUILD.bazel
```

## Files

- `build_ir.proto`, `emit_bazel.py` — the shared schema + Bazel backend.
- `meson_frontend.py` — meson `introspect --targets` → `BuildGraph` (C/C++).
- `mozbuild_frontend.py` — mozbuild emitter objects (JSON) → `BuildGraph` (C/C++).
- `cargo_frontend.py` — `cargo metadata` → `BuildGraph` (Rust → rules_rust); the
  third frontend, so Rust/Cargo projects (e.g. Servo) come up via the same IR.
- `mozbuild_backend.py` — the `./mach build-backend -b BuildIR` backend that
  produces that JSON from a configured mozilla-central.
- `emit_kythe.py` — Layer-A down-projection: `BuildGraph` → Kythe
  `CompilationUnit`s (the seam to the source symbol graph).
- `validate_partition.py` — the decomposition-validation gate (build-dep cut vs.
  symbol-reference graph).
- `test_*.py` — golden + unit tests, runnable with no meson/bazel/mozilla tree.

## mozbuild frontend — validation status

The mozbuild path is **validated against the real Mozilla object model**
(gecko-dev `python/mozbuild/mozbuild/frontend/{data,emitter}.py`):

- `mozbuild_backend.py` is written against the verified real attributes — context
  = `relsrcdir`, library name = `basename`, program name = `program`, deps =
  `linked_libraries` (resolved `Library` objects, keyed by `.basename`, **not** the
  raw `USE_LIBS` strings), `Sources.files`, `GeneratedFile.{script,method,inputs,
  outputs}`, `Defines.defines`, `LocalInclude.path`.
- `test_mozbuild_backend.py` feeds `record()` test doubles shaped with those exact
  attributes and confirms the full chain (objects → backend → frontend → Bazel)
  reproduces the golden — so the hand-authored fixture is faithful.

**Residual, pinned by a live run** (needs a configured mozilla-central + one
`./mach build-backend -b BuildIR`): the exact string form of `SourcePath`/`Path`
in the dump (topsrcdir-absolute vs. context-relative). `mozbuild_frontend._ctx_rel`
already normalizes both, but only a live run confirms which Mozilla emits.

## Known gaps (next passes)

- **Generated-source consume edge (meson).** `introspect --targets` does not
  surface a library *consuming* a `custom_target` output (only the codegen step);
  recovering produces→consumes needs the ninja graph (`ninja -t deps`). The
  mozbuild frontend *does* recover it (a source matching a `GeneratedFile` output).
- **Rust / linker libs / system deps / generated-include dirs** — not yet mapped.
- **`translator-core` extraction** — factor the parse→IR→emit+theorem harness
  shared with the CI-config translator.
- **Live `mach` validation** — run the backend on a configured tree (above).
