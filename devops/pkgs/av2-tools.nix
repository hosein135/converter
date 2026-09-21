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

    # GCC 14: RefFrameBuffer uses size_t in the header without <cstddef>, so
    # size() is never declared and av2_mux fails to compile.
    python3 - <<'PY'
from pathlib import Path
p = Path("apps/av2_mux/ref_frame_buffer.h")
if not p.is_file():
    raise SystemExit
text = p.read_text()
if "#include <cstddef>" not in text:
    if "#include <cstdint>" in text:
        text = text.replace("#include <cstdint>", "#include <cstddef>\n#include <cstdint>", 1)
    elif "#include <array>" in text:
        text = text.replace("#include <array>", "#include <array>\n#include <cstddef>", 1)
    else:
        text = text.replace("#pragma once", "#pragma once\n\n#include <cstddef>", 1)
if "size() const" not in text and "slots_" in text:
    needle = "const RefSlot& slot(size_t i) const { return slots_[i]; }"
    if needle in text:
        text = text.replace(
            needle,
            needle + "\n  size_t size() const { return slots_.size(); }",
            1,
        )
p.write_text(text)
PY
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
