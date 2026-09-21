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

  # avmenc is extremely RAM-hungry at high cpu-used values; keep the
  # default Release flags from upstream.
  enableParallelBuilding = true;

  outputs = [
    "out"
    "dev"
  ];

  meta = with lib; {
    description = "AOMedia Video Model — AV2 v1.0.0 reference encoder/decoder";
    homepage = "https://github.com/AOMediaCodec/avm";
    license = licenses.bsd3;
    platforms = platforms.unix;
    mainProgram = "avmenc";
  };
}
