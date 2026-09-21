# SPDX-License-Identifier: MIT
# Dev shell for the AV2 / xHE-AAC converter (Nixpkgs 25.05).
{
  pkgs,
  lib,
  projectRoot,
  avm,
  dav2d-av2,
  exhale,
  av2-tools,
  vlc-av2 ? null,
}:
let
  python = pkgs.python3.withPackages (
    ps: with ps; [
      tkinter
    ]
  );

  pythonBin = "${python}/bin/python";
  pythonSite = "${python}/${python.sitePackages}";

  toolBins = lib.makeBinPath (
    [
      avm
      dav2d-av2
      exhale
      av2-tools
      pkgs.ffmpeg
      pkgs.gpac
    ]
    ++ lib.optional (vlc-av2 != null) vlc-av2
    ++ [
      pkgs.coreutils
      pkgs.curl
      pkgs.git
      pkgs.pkg-config
    ]
  );

  resolveRoot = ''
    resolve_av2converter_root() {
      if [ -n "''${AV2CONVERTER_ROOT:-}" ] && [ -f "''${AV2CONVERTER_ROOT}/src/av2converter/__init__.py" ]; then
        printf '%s\n' "''${AV2CONVERTER_ROOT}"
        return 0
      fi
      local dir="''${PWD}"
      while [ -n "$dir" ] && [ "$dir" != "/" ]; do
        if [ -f "$dir/src/av2converter/__init__.py" ]; then
          printf '%s\n' "$dir"
          return 0
        fi
        dir="$(dirname "$dir")"
      done
      echo "av2-converter: could not find src/av2converter (set AV2CONVERTER_ROOT)" >&2
      return 1
    }
  '';

  exportAppEnv = ''
    ${resolveRoot}
    AV2CONVERTER_ROOT="$(resolve_av2converter_root)"
    export AV2CONVERTER_ROOT
    export PYTHONNOUSERSITE=1
    export PYTHONPATH="''${AV2CONVERTER_ROOT}/src:${pythonSite}''${PYTHONPATH:+:$PYTHONPATH}"
    export AV2CONVERTER_NIX_PYTHON="${pythonBin}"
    if [ -z "''${AV2CONVERTER_DATA_DIR:-}" ]; then
      if [ -d "''${AV2CONVERTER_ROOT}/.av2converter-data" ] || [ -w "''${AV2CONVERTER_ROOT}" ]; then
        export AV2CONVERTER_DATA_DIR="''${AV2CONVERTER_ROOT}/.av2converter-data"
      else
        export AV2CONVERTER_DATA_DIR="''${HOME}/.local/share/av2-converter"
      fi
    fi
    mkdir -p "''${AV2CONVERTER_DATA_DIR}"
    export PATH="${python}/bin:${toolBins}:$PATH"
    export PKG_CONFIG_PATH="${dav2d-av2}/lib/pkgconfig''${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
    ${lib.optionalString (vlc-av2 != null) ''
      export VLC_AV2="''${VLC_AV2:-${vlc-av2}/bin/vlc-av2}"
      if [ ! -x "''${VLC_AV2}" ] && [ -x "${vlc-av2}/bin/vlc" ]; then
        export VLC_AV2="${vlc-av2}/bin/vlc"
      fi
    ''}
  '';

  converter = pkgs.writeShellScriptBin "av2-converter" ''
    set -euo pipefail
    ${exportAppEnv}
    exec "${pythonBin}" -m av2converter "$@"
  '';

  shell = pkgs.mkShell {
    packages = [
      python
      converter
      avm
      dav2d-av2
      exhale
      av2-tools
      pkgs.ffmpeg
      pkgs.gpac
      pkgs.coreutils
      pkgs.curl
      pkgs.git
      pkgs.pkg-config
    ]
    ++ lib.optional (vlc-av2 != null) vlc-av2;

    shellHook = ''
      ${exportAppEnv}
      export AV2CONVERTER_NIX=1
      echo "AV2 converter shell"
      echo "  Python:  $AV2CONVERTER_NIX_PYTHON"
      echo "  Repo:    $AV2CONVERTER_ROOT"
      echo "  Data:    $AV2CONVERTER_DATA_DIR"
      echo "  GUI:     av2-converter"
      echo "  Encode:  avmenc + exhale + av2_mux"
      ${
        if vlc-av2 != null then
          ''echo "  Play:    vlc-av2 (https://github.com/afen261/vlc-av2)"''
        else
          ''echo "  Play:    vlc-av2 is not built on this platform"''
      }
    '';
  };
in
{
  inherit
    python
    converter
    shell
    ;
}
