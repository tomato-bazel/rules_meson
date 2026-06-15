load("@rules_cc//cc:defs.bzl", "cc_binary", "cc_library")
load("@rules_firefox//firefox:defs.bzl", "webidl_library")

webidl_library(
    name = "FooBinding",
    srcs = [
        "dom/bindings/Foo.webidl",
    ],
    outs = [
        "dom/bindings/FooBinding.cpp",
        "dom/bindings/FooBinding.h",
    ],
)

cc_library(
    name = "xpcom",
    srcs = [
        "xpcom/base/nsCOMPtr.cpp",
    ],
)

cc_library(
    name = "dombindings",
    srcs = [
        "dom/bindings/FooBinding.cpp",
        "dom/bindings/BindingUtils.cpp",
        "dom/bindings/FooBinding.h",
    ],
    includes = [
        "dom/bindings",
    ],
    defines = [
        "MOZILLA_INTERNAL_API",
    ],
    deps = [
        ":xpcom",
    ],
)

cc_binary(
    name = "firefox",
    srcs = [
        "browser/app/nsBrowserApp.cpp",
    ],
    deps = [
        ":dombindings",
    ],
)
