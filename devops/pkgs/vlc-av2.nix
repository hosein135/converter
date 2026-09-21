{
  lib,
  stdenv,
  meson,
  ninja,
  pkg-config,
  python3,
  perl,
  bison,
  flex,
  nasm,
  gettext,
  makeWrapper,
  wrapGAppsHook3,
  removeReferencesTo,
  wayland-scanner,

  alsa-lib,
  avahi,
  cairo,
  dbus,
  faad2,
  fdk_aac,
  ffmpeg,
  flac,
  fontconfig,
  freetype,
  fribidi,
  gnutls,
  harfbuzz,
  libarchive,
  libass,
  libGL,
  libplacebo,
  libpulseaudio,
  librsvg,
  libsamplerate,
  libva,
  libvorbis,
  libxml2,
  libxcb,
  xcbutilkeysyms,
  libX11,
  libXext,
  lua5,
  ncurses,
  wayland,
  wayland-protocols,
  zlib,
  libgcrypt,
  libgpg-error,
  libjpeg,
  libpng,
  speex,
  taglib,
  systemdLibs,
  libxkbcommon,
  qt6,

  dav2d-av2,
  src,
  withQt ? true,
}:

stdenv.mkDerivation rec {
  pname = "vlc-av2";
  version = "4.0.0-dev";

  inherit src;

  nativeBuildInputs = [
    meson
    ninja
    pkg-config
    python3
    perl
    bison
    flex
    nasm
    gettext
    makeWrapper
    wrapGAppsHook3
    removeReferencesTo
    wayland-scanner
  ]
  ++ lib.optionals withQt [ qt6.wrapQtAppsHook ];

  buildInputs = [
    dav2d-av2
    alsa-lib
    avahi
    cairo
    dbus
    faad2
    fdk_aac
    ffmpeg
    flac
    fontconfig
    freetype
    fribidi
    gnutls
    harfbuzz
    libarchive
    libass
    libGL
    libplacebo
    libpulseaudio
    librsvg
    libsamplerate
    libva
    libvorbis
    libxml2
    libxcb
    xcbutilkeysyms
    libX11
    libXext
    lua5
    ncurses
    wayland
    wayland-protocols
    zlib
    libgcrypt
    libgpg-error
    libjpeg
    libpng
    speex
    taglib
    systemdLibs
    libxkbcommon
  ]
  ++ lib.optionals withQt (
    with qt6;
    [
      qtbase
      qtdeclarative
      qtsvg
      qtwayland
      qt5compat
      qtshadertools
    ]
  );

  strictDeps = true;

  # VLC 4 currently requires a very new Meson; nixpkgs 25.05 is older.
  # The f-string syntax in meson.build needs Meson >= 1.3, which 25.05 has.
  postPatch = ''
    substituteInPlace meson.build \
      --replace-fail "meson_version: '>=1.10.0')" "meson_version: '>=1.3.0')"

    if ! grep -q "option('dav2d'" meson_options.txt; then
      cat >> meson_options.txt <<'EOF'

option('dav2d',
    type : 'feature',
    value : 'auto',
    description : 'libdav2d AV2 decoder support')
EOF
    fi

    python3 - <<'PY'
from pathlib import Path
import re
p = Path("modules/codec/meson.build")
text = p.read_text()
if "files('dav2d.c')" in text:
    raise SystemExit
insert = """
# dav2d AV2 decoder (vlc-av2)
dav2d_dep = dependency('dav2d', version: '>= 1.0.0', required: get_option('dav2d'))
vlc_modules += {
    'name' : 'dav2d',
    'sources' : files('dav2d.c'),
    'dependencies' : [dav2d_dep],
    'enabled' : dav2d_dep.found(),
}
"""
new, n = re.subn(
    r"(vlc_modules \+= \{[^}]*'name'\s*:\s*'dav1d'[^}]*\})",
    r"\1\n" + insert,
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    # Last-resort append so the derivation still configures.
    new = text.rstrip() + "\n" + insert + "\n"
p.write_text(new)
PY
  '';

  mesonFlags = [
    "-Dvlc=true"
    "-Dtests=disabled"
    "-Dnls=disabled"
    "-Dupdate-check=disabled"
    "-Drust=disabled"
    "-Dchromecast=disabled"
    "-Dskins2=disabled"
    "-Dlua=disabled"
    "-Dmedialibrary=disabled"
    "-Dlive555=disabled"
    "-Dgoom2=disabled"
    "-Dprojectm=disabled"
    "-Dopencv=disabled"
    "-Ddecklink=disabled"
    "-Dfreerdp=disabled"
    "-Dvnc=disabled"
    "-Dgme=disabled"
    "-Dsid=disabled"
    "-Darchive=disabled"
    "-Dsftp=disabled"
    "-Dnfs=disabled"
    "-Ddsm=disabled"
    "-Ddav1d=disabled"
    "-Ddav2d=enabled"
    "-Dfdk-aac=enabled"
    "-Dfaad=enabled"
    "-Davcodec=enabled"
    "-Davformat=enabled"
    "-Dswscale=enabled"
    "-Dqt=${if withQt then "enabled" else "disabled"}"
    "-Dxcb=enabled"
    "-Dx11=enabled"
    "-Dwayland=auto"
    "-Dpulse=auto"
    "-Dalsa=auto"
    "-Dfreetype=auto"
    "-Dfontconfig=auto"
    "-Dpng=enabled"
  ];

  dontWrapGApps = true;

  env.PKG_CONFIG_PATH = "${dav2d-av2}/lib/pkgconfig";

  preFixup = lib.optionalString withQt ''
    qtWrapperArgs+=("''${gappsWrapperArgs[@]}")
    qtWrapperArgs+=(--prefix LD_LIBRARY_PATH : "${dav2d-av2}/lib")
  '';

  postInstall = ''
    mkdir -p $out/bin
    if [ -x $out/bin/vlc ] && [ ! -e $out/bin/vlc-av2 ]; then
      ln -s vlc $out/bin/vlc-av2
    fi
    # Touch plugins so vlc-cache-gen is stable (mtime-based cache).
    if [ -d $out/lib/vlc/plugins ]; then
      find $out/lib/vlc/plugins -exec touch -d @1 '{}' ';' || true
      if [ -x $out/lib/vlc/vlc-cache-gen ]; then
        $out/lib/vlc/vlc-cache-gen $out/lib/vlc/plugins || true
      fi
    fi
  '';

  meta = with lib; {
    description = "Experimental VLC 4 fork with AV2 playback via dav2d-av2";
    homepage = "https://github.com/afen261/vlc-av2";
    license = licenses.gpl2Plus;
    platforms = platforms.linux;
    mainProgram = "vlc-av2";
  };
}
