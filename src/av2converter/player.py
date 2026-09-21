from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from av2converter.paths import which


class PlayerError(RuntimeError):
    pass


def vlc_av2_binary() -> str:
    found = which("vlc-av2", "VLC_AV2")
    if found:
        return found
    found = which("vlc")
    if found:
        return found
    raise PlayerError(
        "vlc-av2 was not found on PATH. Rebuild the Nix environment "
        "(./run.sh --force-setup) or set VLC_AV2 to the player binary.\n"
        "https://github.com/afen261/vlc-av2"
    )


def open_in_vlc_av2(path: str | Path) -> subprocess.Popen:
    media = Path(path)
    if not media.is_file():
        raise PlayerError(f"File not found: {media}")
    binary = vlc_av2_binary()
    env = os.environ.copy()
    # Prefer the dav2d-av2 library from the Nix shell when present.
    cmd = [binary, "--started-from-file", str(media)]
    kwargs: dict = {
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
    }
    return subprocess.Popen(cmd, **kwargs)


def reveal_in_file_manager(path: str | Path) -> None:
    media = Path(path)
    folder = str(media.parent)
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(media)])
        return
    opener = shutil.which("xdg-open")
    if opener:
        subprocess.Popen([opener, folder])
