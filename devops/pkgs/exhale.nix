{
  lib,
  stdenv,
  src,
}:

stdenv.mkDerivation rec {
  pname = "exhale";
  version = "1.2.2";

  inherit src;

  # Upstream ships GNU makefiles (src/lib + src/app). "make release"
  # writes the encoder into bin/.
  buildPhase = ''
    runHook preBuild
    make -j$NIX_BUILD_CORES release
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    mkdir -p $out/bin
    found="$(find bin -type f -name exhale | head -1)"
    if [ -z "$found" ]; then
      echo "exhale binary was not produced in bin/" >&2
      find bin -type f >&2 || true
      exit 1
    fi
    install -m755 "$found" $out/bin/exhale
    runHook postInstall
  '';

  meta = with lib; {
    description = "Open-source xHE-AAC / USAC encoder";
    homepage = "https://gitlab.com/ecodis/exhale";
    license = licenses.bsd3;
    platforms = platforms.unix;
    mainProgram = "exhale";
  };
}
