"""Module extension fetching hermetic meson + ninja.

meson is pure Python (no third-party deps). We expose its source as a
`py_library` so consumers can `import mesonbuild.mesonmain` directly —
this avoids nested py_binary subprocesses, which fight Bazel's
runfiles-discovery semantics.

ninja is a prebuilt single-binary zip from the upstream GitHub release.
We extract and expose it as a label; the meson_configure rule puts its
directory on PATH for meson's subprocess to find it.

We deliberately do NOT use rules_foreign_cc's meson + ninja toolchains.
Those are designed to be driven by rules_foreign_cc's own build-script
framework (which sets EXT_BUILD_ROOT and orchestrates runfiles). Using
them outside that framework hits walls; this fetch-and-go pattern is
simpler and a better fit for "just run meson setup, capture the
compdb."
"""

# Pinned versions. Bump deliberately; recompute sha256 from the upstream
# release artifact:
#   meson:  curl -fsSL <url> | shasum -a 256
#   ninja:  same.
_MESON_VERSION = "1.7.1"
_MESON_SHA256 = "155780a5be87f6dd7f427ad8bcbf0f2b2c5f62ee5fdacca7caa9de8439a24b89"
_MESON_URL = (
    "https://github.com/mesonbuild/meson/releases/download/" +
    "{v}/meson-{v}.tar.gz"
).format(v = _MESON_VERSION)

_NINJA_VERSION = "1.12.1"

# Per-OS prebuilt ninja from the upstream GitHub release, keyed by the
# `rctx.os.name` family. ninja-mac.zip is a universal binary (x86_64 + arm64);
# ninja-linux.zip is x86_64. (Linux arm64 would need ninja-linux-aarch64.zip;
# Windows ninja-win.zip — add when a CI exercises them.)
_NINJA_ASSETS = {
    "mac": ("ninja-mac.zip", "89a287444b5b3e98f88a945afa50ce937b8ffd1dcc59c555ad9b1baf855298c9"),
    "linux": ("ninja-linux.zip", "6f98805688d19672bd699fbbfa2c2cf0fc054ac3df1f0e6a47664d963d530255"),
}

def _ninja_asset(rctx):
    name = rctx.os.name.lower()
    if name.startswith("mac"):
        return _NINJA_ASSETS["mac"]
    if name.startswith("linux"):
        return _NINJA_ASSETS["linux"]
    fail("rules_meson: no prebuilt ninja {v} for OS '{n}'".format(v = _NINJA_VERSION, n = rctx.os.name))

_MESON_BUILD = """
load("@rules_python//python:py_library.bzl", "py_library")

package(default_visibility = ["//visibility:public"])

# The mesonbuild Python package — meson's entire implementation. Pure
# Python, no third-party deps. Consumed as a py_library so consumers
# can `import mesonbuild.mesonmain` and invoke meson in-process without
# nested py_binary subprocesses.
py_library(
    name = "mesonbuild",
    srcs = glob(
        ["mesonbuild/**/*.py"],
        allow_empty = False,
    ),
    data = glob(
        # mesonbuild ships data files (.in templates, JSON schemas) it
        # reads at runtime; include them all conservatively.
        [
            "mesonbuild/**/*.in",
            "mesonbuild/**/*.json",
            "mesonbuild/**/*.txt",
            "mesonbuild/**/data/**",
        ],
        allow_empty = True,
    ),
    imports = ["."],
)
"""

_NINJA_BUILD = """
package(default_visibility = ["//visibility:public"])

# The prebuilt ninja binary, extracted from the per-OS ninja release zip. Used by
# meson_configure as a tool — its dirname goes on PATH so meson's
# subprocess can find `ninja` when looking for a build backend.
exports_files(["ninja"])

filegroup(
    name = "ninja_bin",
    srcs = ["ninja"],
)
"""

def _meson_dist_impl(rctx):
    rctx.download_and_extract(
        url = _MESON_URL,
        sha256 = _MESON_SHA256,
        stripPrefix = "meson-" + _MESON_VERSION,
    )
    rctx.file("BUILD.bazel", _MESON_BUILD)

_meson_dist_repository = repository_rule(
    implementation = _meson_dist_impl,
    doc = "Fetch the meson source tarball and expose it as @meson_dist//:mesonbuild.",
)

def _ninja_dist_impl(rctx):
    asset, sha256 = _ninja_asset(rctx)
    rctx.download_and_extract(
        url = "https://github.com/ninja-build/ninja/releases/download/v{v}/{a}".format(
            v = _NINJA_VERSION,
            a = asset,
        ),
        sha256 = sha256,
    )

    # zip extraction doesn't reliably preserve the +x bit; ensure ninja runs.
    rctx.execute(["chmod", "0755", "ninja"])
    rctx.file("BUILD.bazel", _NINJA_BUILD)

_ninja_dist_repository = repository_rule(
    implementation = _ninja_dist_impl,
    doc = "Fetch the prebuilt ninja binary and expose it as @ninja_dist//:ninja.",
)

def _meson_tools_impl(_mctx):
    _meson_dist_repository(name = "meson_dist")
    _ninja_dist_repository(name = "ninja_dist")

meson_tools = module_extension(
    implementation = _meson_tools_impl,
    doc = "Fetch hermetic meson + ninja for the meson_configure rule.",
)
