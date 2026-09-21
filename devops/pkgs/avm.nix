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
  # broken avm.pc.
  postPatch = ''
    python3 ${./avm-fix-install.py}
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
