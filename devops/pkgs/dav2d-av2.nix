{
  lib,
  stdenv,
  meson,
  ninja,
  nasm,
  pkg-config,
  xxHash,
  python3,
  src,
}:

stdenv.mkDerivation rec {
  pname = "dav2d-av2";
  version = "unstable";

  inherit src;

  outputs = [
    "out"
    "dev"
  ];

  nativeBuildInputs = [
    meson
    ninja
    nasm
    pkg-config
    python3
  ];

  buildInputs = [ xxHash ];

  mesonFlags = [
    "-Denable_tools=true"
    "-Denable_examples=false"
    "-Denable_tests=false"
  ];

  # Upstream tests need a separate testdata checkout.
  doCheck = false;

  meta = with lib; {
    description = "dav2d fork with AV2 v1.0.0 adaptive CCSO decoding";
    homepage = "https://github.com/afen261/dav2d-av2";
    license = licenses.bsd2;
    platforms = platforms.unix;
    mainProgram = "dav2d";
  };
}
