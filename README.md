# rules_meson

Hermetic **meson + ninja** for Bazel — build meson projects reproducibly under
Bazel with pinned, downloaded meson/ninja toolchains.

## Use it

```starlark
# MODULE.bazel — resolves from the fastverk registry (registry.fastverk.com)
bazel_dep(name = "rules_meson", version = "0.0.0")
```

See the package `BUILD.bazel` / `defs.bzl` for the rules. Part of the
tomato-bazel distribution.
