project('hello', 'c')

# Tiniest meson project that still produces a compile_commands.json
# entry. Validates the rules_meson toolchain end-to-end: meson is
# importable, ninja is on PATH, the runner orchestrates correctly,
# the compdb gets relativized.
#
# We use library() instead of executable() so the smoke test doesn't
# depend on a working linker — meson_configure only runs `setup`, not
# build, but library() is cheaper to introspect later (no need for the
# host's linker to be probed).
library('hello', 'hello.c')
run_command(find_program('roma_aux_probe'), check: true)
custom_target('generated_header',
  output: 'generated.h',
  command: [find_program('roma_aux_probe'), '@OUTPUT@'])
