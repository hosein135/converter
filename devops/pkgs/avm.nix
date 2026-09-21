{
  lib,
  stdenv,
  cmake,
  nasm,
  yasm,
  perl,
  python3,
  pkg-config,
  git,
  src,
}:

stdenv.mkDerivation rec {
  pname = "avm";
  version = "1.0.0";

  inherit src;

  nativeBuildInputs = [
    cmake
    nasm
    yasm
    perl
    python3
    pkg-config
    git
  ];

  # AVM refuses in-tree builds; the Nix cmake setup already uses a build dir.
  cmakeFlags = [
    "-DBUILD_SHARED_LIBS=ON"
    "-DENABLE_TESTS=OFF"
    "-DENABLE_DOCS=OFF"
    "-DENABLE_EXAMPLES=ON"
    "-DENABLE_TOOLS=OFF"
  ];

  # The build calls `git describe` to stamp the library version.
  preConfigure = ''
    cat > "$NIX_BUILD_TOP/git" <<EOF
    #!${stdenv.shell}
    echo v${version}
    EOF
    chmod +x "$NIX_BUILD_TOP/git"
    export PATH="$NIX_BUILD_TOP:$PATH"
  '';

  # AVM joins CMAKE_INSTALL_PREFIX onto GNUInstallDirs paths. Nix already
  # passes those as absolute store paths, which produced $out/$out/... and a
  # broken avm.pc (`includedir=${prefix}//nix/store/...`).
  postPatch = ''
    python3 - <<'PY'
from pathlib import Path

install = Path("cmake/avm_install.cmake")
text = install.read_text()
repls = [
    (
        'DESTINATION "${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_INCLUDEDIR}/avm")',
        'DESTINATION "${CMAKE_INSTALL_FULL_INCLUDEDIR}/avm")',
    ),
    (
        'DESTINATION "${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR}/pkgconfig")',
        'DESTINATION "${CMAKE_INSTALL_FULL_LIBDIR}/pkgconfig")',
    ),
    (
        'DESTINATION "${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR}")',
        'DESTINATION "${CMAKE_INSTALL_FULL_LIBDIR}")',
    ),
    (
        'DESTINATION "${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_BINDIR}")',
        'DESTINATION "${CMAKE_INSTALL_FULL_BINDIR}")',
    ),
    (
        "-DCMAKE_INSTALL_INCLUDEDIR=${CMAKE_INSTALL_INCLUDEDIR}",
        "-DCMAKE_INSTALL_FULL_INCLUDEDIR=${CMAKE_INSTALL_FULL_INCLUDEDIR}",
    ),
    (
        "-DCMAKE_INSTALL_LIBDIR=${CMAKE_INSTALL_LIBDIR}",
        "-DCMAKE_INSTALL_FULL_LIBDIR=${CMAKE_INSTALL_FULL_LIBDIR}",
    ),
]
for old, new in repls:
    if old not in text:
        raise SystemExit(f"avm_install.cmake: missing {old!r}")
    text = text.replace(old, new)
install.write_text(text)

pc = Path("cmake/pkg_config.cmake")
pct = pc.read_text()
pct = pct.replace(
    '"CMAKE_INSTALL_INCLUDEDIR"',
    '"CMAKE_INSTALL_FULL_INCLUDEDIR"',
)
pct = pct.replace(
    '"CMAKE_INSTALL_LIBDIR"',
    '"CMAKE_INSTALL_FULL_LIBDIR"',
)
old_block = """set(prefix "${CMAKE_INSTALL_PREFIX}")
set(bindir "${CMAKE_INSTALL_BINDIR}")
set(includedir "${CMAKE_INSTALL_INCLUDEDIR}")
set(libdir "${CMAKE_INSTALL_LIBDIR}")"""
new_block = """get_filename_component(prefix "${CMAKE_INSTALL_FULL_INCLUDEDIR}" DIRECTORY)
get_filename_component(exec_prefix "${CMAKE_INSTALL_FULL_LIBDIR}" DIRECTORY)
get_filename_component(includedir "${CMAKE_INSTALL_FULL_INCLUDEDIR}" NAME)
get_filename_component(libdir "${CMAKE_INSTALL_FULL_LIBDIR}" NAME)"""
if old_block not in pct:
    raise SystemExit("pkg_config.cmake: install-dir block not found")
pct = pct.replace(old_block, new_block)
pct = pct.replace(
    'file(APPEND "${pkgconfig_file}" "exec_prefix=\\${prefix}\\n")',
    'file(APPEND "${pkgconfig_file}" "exec_prefix=${exec_prefix}\\n")',
)
pc.write_text(pct)
PY
  '';

  # avmenc is extremely RAM-hungry at high cpu-used values; keep the
  # default Release flags from upstream.
  enableParallelBuilding = true;

  postInstall = ''
    if [ -d "$out/nix/store" ]; then
      nested="$(find "$out/nix/store" -mindepth 1 -maxdepth 1 -type d | head -1)"
      echo "Flattening nested AVM prefix: $nested"
      cp -a "$nested"/. "$out"/
      rm -rf "$out/nix"
    fi
    pc="$(find "$out" -name avm.pc | head -1 || true)"
    if [ -n "$pc" ]; then
      sed -i -e 's|\''${prefix}//|/|g' -e 's|\''${exec_prefix}//|/|g' -e 's|//nix/store|/nix/store|g' "$pc"
    fi
  '';

  # Keep a single output. Splitting out/dev makes avm.pc and the shared
  # library point at each other, which Nix rejects as a reference cycle.

  meta = with lib; {
    description = "AOMedia Video Model — AV2 v1.0.0 reference encoder/decoder";
    homepage = "https://github.com/AOMediaCodec/avm";
    license = licenses.bsd3;
    platforms = platforms.unix;
    mainProgram = "avmenc";
  };
}
