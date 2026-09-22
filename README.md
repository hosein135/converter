# AV2 Converter

Desktop GUI that transcodes a video file to **AV2** (AOMedia AVM reference encoder) and its audio to **xHE-AAC** (exhale), then plays finished files in [vlc-av2](https://github.com/afen261/vlc-av2).

The project is started the same way as LibreLane: **`./run.sh`** bootstraps curl + Nix if needed, then enters a **Nixpkgs 25.05** flake that provides every tool.

## Quick start

On a Linux VM (or macOS):

```bash
chmod +x run.sh
./run.sh
```

```bash
./run.sh --prep-only         # build tools, do not open the GUI
./run.sh --force-setup       # drop the cached Nix env and rebuild
./run.sh --convert clip.mp4  # headless convert
```

First run compiles AVM (`avmenc`), dav2d-av2, exhale, and the vlc-av2 player from source. That can take a long time and several GB of disk.

## What the GUI does

**Convert tab**

1. Choose a source video.
2. Optional speed, quality, and xHE-AAC mode. Resolution, frame rate, and bit depth are left as in the source.
3. Convert:
   - ffmpeg decodes video to Y4M and audio to 48 kHz WAV
   - `avmenc` encodes **AV2**
   - `av2_mux` (or the built-in muxer) wraps AV2 as MP4 (`av02` + `av2C`)
   - `exhale` encodes **xHE-AAC**
   - MP4Box / ffmpeg copies both tracks into one `.mp4`

**Converted tab**

- Lists finished files.
- **Double-click** (or Enter / Play) opens the file with **vlc-av2**  
  <https://github.com/afen261/vlc-av2>

vlc-av2 is an unofficial VLC 4 fork that software-decodes AV2 through [dav2d-av2](https://github.com/afen261/dav2d-av2). It is experimental.

## Layout

```
run.sh                 # curl + Nix 2.24 + flake cache + launch GUI
devops/flake.nix       # nixpkgs 25.05 + tool sources
devops/shell.nix
devops/pkgs/           # avm, dav2d-av2, exhale, av2-tools, vlc-av2
src/av2converter/      # Tk GUI + convert / mux / library
```

Converted files and the library index live in `.av2converter-data/` (or `AV2CONVERTER_DATA_DIR`).

## Manual Nix shell

```bash
nix develop devops --accept-flake-config
av2-converter
```

## Notes

- AVM is a **reference** encoder, so it is slower than a production encoder. The converter uses every CPU, `cpu-used` 9, and a reduced partition search. Higher **cpu-used** is faster.
- xHE-AAC encoding uses [exhale](https://gitlab.com/ecodis/exhale). Modes `0`–`9` are CVBR without SBR; `a`–`g` enable SBR.
- This repository is not affiliated with VideoLAN or AOMedia.
