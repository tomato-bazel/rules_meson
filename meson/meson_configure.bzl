"""`meson_configure` — hermetic `meson setup` for any meson-built source tree.

Captures `compile_commands.json` from running meson against a labeled
source tree. Uses hermetic meson + ninja vendored by meson_tools.bzl;
no system PATH dependency. Output paths are relativized to be portable
across Bazel sandboxes.

Use directly for general meson projects:

    load("@rules_meson//meson:meson_configure.bzl", "meson_configure")

    meson_configure(
        name = "myproj_compdb",
        srcs = ["@myproj//:all_source"],
        marker = "@myproj//:meson.build",
    )

Or via a wrapper macro that supplies project-specific defaults. The
canonical example is rules_postgres's `pg_meson_configure`, which sets
PG-tailored meson_options and pre_remove paths.

For consumers that need to introspect meson's target graph (the M2
work), `meson introspect --targets <build>` is the right call. That
output isn't captured by this rule yet — see project memory
`project_postgres_bazel_native` for the M1+ extension.
"""

def _meson_configure_impl(ctx):
    if not ctx.files.srcs:
        fail("meson_configure(%s): 'srcs' must be non-empty" % ctx.label)

    # Derive the in-sandbox source root from the marker file's path.
    marker_path = ctx.file.marker.path
    last_slash = marker_path.rfind("/")
    if last_slash <= 0:
        fail("meson_configure(%s): can't derive source root from " % ctx.label +
             "marker path %r" % marker_path)
    src_root = marker_path[:last_slash]

    out_compdb = ctx.actions.declare_file(ctx.label.name + ".compile_commands.json")
    out_log = ctx.actions.declare_file(ctx.label.name + ".meson.log")
    out_introspect = ctx.actions.declare_file(ctx.label.name + ".introspect.json")
    out_headers = ctx.actions.declare_directory(ctx.label.name + ".headers")

    args = ctx.actions.args()
    args.add("--src-root", src_root)
    args.add("--out-compdb", out_compdb.path)
    args.add("--out-log", out_log.path)
    args.add("--out-introspect", out_introspect.path)
    args.add("--out-headers-dir", out_headers.path)
    args.add("--ninja-bin", ctx.file._ninja.path)
    for tool in ctx.files.auxiliary_tools:
        args.add("--tool-bin", tool.path)
    auxiliary_data = []
    for target, name in ctx.attr.auxiliary_tool_environment.items():
        files = target.files.to_list()
        if len(files) != 1:
            fail("auxiliary tool environment %s must name one file or directory" % name)
        auxiliary_data.append(files[0])
        args.add("--tool-env", name + "=" + files[0].path)
    for opt in ctx.attr.meson_options:
        # `=` form so values starting with `-` don't trip argparse.
        args.add("--meson-option=" + opt)
    for rel in ctx.attr.pre_remove:
        args.add("--pre-remove=" + rel)
    if ctx.attr.build_custom_targets:
        args.add("--build-custom-targets")
    for output in ctx.attr.required_custom_outputs:
        args.add("--required-custom-output", output)

    ctx.actions.run(
        executable = ctx.executable._meson_runner,
        outputs = [out_compdb, out_log, out_introspect, out_headers],
        inputs = depset(ctx.files.srcs + ctx.files.auxiliary_tools + auxiliary_data + [ctx.file.marker, ctx.file._ninja]),
        arguments = [args],
        mnemonic = "MesonConfigure",
        progress_message = "Running meson setup against %s" % src_root,
    )

    return [
        # Single-file default so downstream consumers (rules whose attrs
        # use `allow_single_file = [".json"]`) resolve `:<target>` to
        # the compdb directly.
        DefaultInfo(files = depset([out_compdb])),
        OutputGroupInfo(
            compile_commands = depset([out_compdb]),
            log = depset([out_log]),
            introspect = depset([out_introspect]),
            # Headers go into a TreeArtifact downstream consumers consume
            # via `filegroup(srcs = [":<name>"], output_group = "headers")`
            # or by directly referencing the rule and inspecting outputs.
            headers = depset([out_headers]),
        ),
    ]

meson_configure = rule(
    implementation = _meson_configure_impl,
    attrs = {
        "srcs": attr.label_list(
            allow_files = True,
            mandatory = True,
            doc = "Every file in the source tree meson should see. " +
                  "Typically a glob filegroup over the full source root.",
        ),
        "marker": attr.label(
            allow_single_file = True,
            mandatory = True,
            doc = "Label of the meson.build file at the source root. " +
                  "Used to derive the source tree's sandbox path " +
                  "(meson takes a positional source-dir arg).",
        ),
        "meson_options": attr.string_list(
            default = ["-Dbuildtype=debug"],
            doc = "Flags passed to `meson setup` after build_dir + " +
                  "src_root. Wrappers (e.g. pg_meson_configure) supply " +
                  "project-specific defaults; bare meson_configure uses " +
                  "just `-Dbuildtype=debug`.",
        ),
        "pre_remove": attr.string_list(
            default = [],
            doc = "Source-root-relative paths the runner deletes before " +
                  "invoking meson. Generic mechanism for projects whose " +
                  "source tree carries files that confuse meson's " +
                  "clean-checkout heuristic (e.g. Postgres' autoconf-" +
                  "style pg_config.h overlay).",
        ),
        "required_custom_outputs": attr.string_list(
            doc = "Build-directory-relative Meson custom output paths to generate. " +
                  "When populated, only these outputs are requested and generation failures fail the action.",
        ),
        "build_custom_targets": attr.bool(
            default = False,
            doc = "If True, after `meson setup` runs ninja to execute " +
                  "every custom_target the project declares. Required " +
                  "for codebases whose TUs #include headers produced by " +
                  "code-generation scripts (e.g. Postgres' Perl " +
                  "`generate-errcodes.pl`). Only custom_target outputs " +
                  "are built (no object files, no link step), so wall-" +
                  "clock cost stays bounded. Failures with `-k 0` are " +
                  "non-fatal: partial codegen still useful (frontend " +
                  "files generated even if backend ones fail).",
        ),
        "auxiliary_tools": attr.label_list(
            allow_files = True,
            cfg = "exec",
            doc = "Files whose parent directories are added to the configure and code generation PATH.",
        ),
        "auxiliary_tool_environment": attr.label_keyed_string_dict(
            allow_files = True,
            cfg = "exec",
            doc = "Single-file or directory labels mapped to environment variable names for auxiliary tools.",
        ),
        "_meson_runner": attr.label(
            default = "//meson/private:meson_runner",
            executable = True,
            cfg = "exec",
        ),
        "_ninja": attr.label(
            default = "@ninja_dist//:ninja",
            allow_single_file = True,
        ),
    },
    doc = "Hermetic `meson setup` runner; outputs compile_commands.json + " +
          "a log of the configure step.",
)
