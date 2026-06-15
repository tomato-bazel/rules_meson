load("@rules_rust//rust:defs.bzl", "rust_binary", "rust_library")

rust_library(
    name = "greet",
    srcs = [
        "greet/src/lib.rs",
    ],
    edition = "2021",
)

rust_binary(
    name = "app",
    srcs = [
        "app/src/main.rs",
    ],
    edition = "2021",
    deps = [
        ":greet",
    ],
)
