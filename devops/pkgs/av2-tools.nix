{
  lib,
  stdenv,
  cmake,
  git,
  python3,
  pkg-config,
  src,
  cli11Src,
  spdlogSrc,
  nlohmannJsonSrc,
  isobmffSrc,
}:

stdenv.mkDerivation rec {
  pname = "av2-tools";
  version = "unstable";

  inherit src;

  nativeBuildInputs = [
    cmake
    git
    python3
    pkg-config
  ];

  postPatch = ''
    # Nix store sources are read-only; do not write generated TS into the tree.
    substituteInPlace CMakeLists.txt \
      --replace-fail \
        "configure_file(cmake/web_version.ts.in \''${CMAKE_SOURCE_DIR}/web/src/generated/version.ts @ONLY)" \
        "# skipped web_version.ts (read-only Nix source)"
  '';

  cmakeFlags = [
    "-DCMAKE_BUILD_TYPE=Release"
    "-DBUILD_CONTAINER_TOOLS=ON"
    "-DBUILD_TESTS=OFF"
    "-DBUILD_EXAMPLES=OFF"
    "-DBUILD_WASM=OFF"
    "-DJSON_BuildTests=OFF"
    "-DSPDLOG_BUILD_TESTS=OFF"
    "-DSPDLOG_BUILD_EXAMPLE=OFF"
    "-DCLI11_BUILD_TESTS=OFF"
    "-DCLI11_BUILD_EXAMPLES=OFF"
    "-DISOBMFF_BUILD_LIB_ONLY=ON"
    "-DFETCHCONTENT_FULLY_DISCONNECTED=ON"
    "-DFETCHCONTENT_SOURCE_DIR_CLI11=${cli11Src}"
    "-DFETCHCONTENT_SOURCE_DIR_SPDLOG=${spdlogSrc}"
    "-DFETCHCONTENT_SOURCE_DIR_NLOHMANN_JSON=${nlohmannJsonSrc}"
    "-DFETCHCONTENT_SOURCE_DIR_LIBISOMEDIA=${isobmffSrc}"
  ];

  postInstall = ''
    mkdir -p $out/bin
    find . -type f -perm -111 \( -name av2_mux -o -name av2_demux -o -name av2_obu_tool \) \
      -exec install -m755 {} $out/bin/ \; || true
  '';

  meta = with lib; {
    description = "AOMedia AV2 OBU tools and ISOBMFF muxer (av2_mux)";
    homepage = "https://github.com/AOMediaCodec/av2-tools";
    license = licenses.bsd3;
    platforms = platforms.unix;
    mainProgram = "av2_mux";
  };
}
