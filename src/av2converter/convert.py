from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from av2converter import library
from av2converter.mux import MuxError, ivf_to_av2_mp4, merge_audio
from av2converter.paths import converted_dir, which

LogFn = Callable[[str], None]


class ConvertError(RuntimeError):
    pass


@dataclass
class ConvertSettings:
    cpu_used: int = 8
    cq_level: int = 32
    bit_depth: int = 10
    max_width: int = 1280
    audio_mode: str = "5"  # exhale CVBR 0-9 / a-g
    keep_work: bool = False


def _run(
    cmd: list[str],
    log: LogFn,
    *,
    cwd: Path | None = None,
) -> None:
    log("$ " + " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log(line.rstrip())
    code = proc.wait()
    if code != 0:
        raise ConvertError(f"Command failed ({code}): {' '.join(cmd)}")


def _ffprobe(path: Path) -> dict:
    binary = which("ffprobe") or which("ffmpeg")
    if not binary:
        raise ConvertError("ffprobe/ffmpeg is not on PATH")
    if Path(binary).name.startswith("ffmpeg"):
        # ffmpeg can still print stream info, but prefer ffprobe.
        ffprobe = which("ffprobe")
        if ffprobe:
            binary = ffprobe
        else:
            raise ConvertError("ffprobe is not on PATH")
    cmd = [
        binary,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ConvertError(proc.stderr or "ffprobe failed")
    return json.loads(proc.stdout or "{}")


def _stream(info: dict, kind: str) -> dict | None:
    for stream in info.get("streams") or []:
        if stream.get("codec_type") == kind:
            return stream
    return None


def _fps(stream: dict | None) -> tuple[int, int]:
    if not stream:
        return 30, 1
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = stream.get(key) or ""
        if raw and raw != "0/0":
            if "/" in raw:
                num, den = raw.split("/", 1)
                try:
                    n, d = int(num), int(den)
                    if n > 0 and d > 0:
                        return n, d
                except ValueError:
                    pass
    return 30, 1


def _scale_filter(stream: dict | None, max_width: int) -> str | None:
    if max_width <= 0 or not stream:
        return None
    try:
        width = int(stream.get("width") or 0)
    except (TypeError, ValueError):
        width = 0
    if width <= max_width:
        return None
    return f"scale={max_width}:-2"


def convert_file(
    source: str | Path,
    *,
    output: str | Path | None = None,
    settings: ConvertSettings | None = None,
    log: LogFn | None = None,
) -> Path:
    settings = settings or ConvertSettings()
    log = log or (lambda _line: None)
    src = Path(source).expanduser().resolve()
    if not src.is_file():
        raise ConvertError(f"Source not found: {src}")

    ffmpeg = which("ffmpeg")
    avmenc = which("avmenc")
    exhale = which("exhale")
    av2_mux = which("av2_mux")
    if not ffmpeg:
        raise ConvertError("ffmpeg is not on PATH (enter via ./run.sh)")
    if not avmenc:
        raise ConvertError("avmenc is not on PATH — AVM did not build")
    if not exhale:
        raise ConvertError("exhale is not on PATH — xHE-AAC encoder missing")

    info = _ffprobe(src)
    video = _stream(info, "video")
    audio = _stream(info, "audio")
    if video is None:
        raise ConvertError("No video stream in the source file")

    fps_num, fps_den = _fps(video)
    dest = Path(output).expanduser() if output else converted_dir() / f"{src.stem}.av2.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)

    pix = "yuv420p10le" if settings.bit_depth >= 10 else "yuv420p"
    vf = _scale_filter(video, settings.max_width)

    work = Path(tempfile.mkdtemp(prefix="av2converter-"))
    try:
        y4m = work / "video.y4m"
        wav = work / "audio.wav"
        ivf = work / "video.ivf"
        obu = work / "video.obu"
        audio_m4a = work / "audio.m4a"
        video_mp4 = work / "video.mp4"

        log("Decoding video to Y4M for the AV2 reference encoder…")
        decode_video = [
            ffmpeg,
            "-y",
            "-i",
            str(src),
            "-an",
            "-pix_fmt",
            pix,
        ]
        if pix == "yuv420p10le":
            decode_video += ["-strict", "unofficial"]
        if vf:
            decode_video += ["-vf", vf]
            log(f"Scaling filter: {vf}")
        decode_video += [str(y4m)]
        _run(decode_video, log)

        if audio is not None:
            log("Decoding audio to 48 kHz stereo WAV for exhale…")
            _run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(src),
                    "-vn",
                    "-ac",
                    "2",
                    "-ar",
                    "48000",
                    "-c:a",
                    "pcm_s16le",
                    str(wav),
                ],
                log,
            )

        log(
            f"Encoding AV2 with AVM avmenc (cpu-used={settings.cpu_used}, "
            f"cq={settings.cq_level}). This is a reference encoder and can be slow."
        )
        encode = [
            avmenc,
            f"--cpu-used={settings.cpu_used}",
            "--end-usage=q",
            f"--cq-level={settings.cq_level}",
            f"--bit-depth={settings.bit_depth}",
            f"--fps={fps_num}/{fps_den}",
            "-o",
            str(ivf),
            str(y4m),
        ]
        try:
            _run(encode, log)
        except ConvertError:
            encode = [
                arg if arg != "--end-usage=q" else "--end-usage=cq" for arg in encode
            ]
            log("Retrying avmenc with --end-usage=cq …")
            _run(encode, log)

        if not ivf.is_file() or ivf.stat().st_size == 0:
            raise ConvertError("avmenc did not produce an IVF bitstream")

        log("Packaging AV2 into MP4 (av02 / av2C) for vlc-av2…")
        muxed = False
        if av2_mux:
            # av2_mux wants an elementary OBU stream. Strip the IVF headers.
            from av2converter.mux import read_ivf

            ivf_video = read_ivf(ivf)
            obu.write_bytes(b"".join(frame.payload for frame in ivf_video.frames))
            fps = f"{fps_num}/{fps_den}"
            try:
                _run(
                    [
                        av2_mux,
                        str(obu),
                        "-o",
                        str(video_mp4),
                        "--fps",
                        fps,
                    ],
                    log,
                )
                muxed = video_mp4.is_file() and video_mp4.stat().st_size > 0
            except ConvertError as exc:
                log(f"av2_mux failed ({exc}); falling back to the built-in muxer.")
        if not muxed:
            ivf_to_av2_mp4(ivf, video_mp4)

        has_audio = audio is not None and wav.is_file()
        if has_audio:
            log(f"Encoding xHE-AAC with exhale (mode {settings.audio_mode})…")
            _run([exhale, str(settings.audio_mode), str(wav), str(audio_m4a)], log)
            if not audio_m4a.is_file():
                raise ConvertError("exhale did not produce an M4A file")
            log("Muxing AV2 video + xHE-AAC audio…")
            try:
                merge_audio(video_mp4, audio_m4a, dest)
            except MuxError as exc:
                log(str(exc))
                log("Keeping video-only MP4.")
                shutil.copy2(video_mp4, dest)
                has_audio = False
        else:
            log("No audio stream — writing video-only AV2 MP4.")
            shutil.copy2(video_mp4, dest)

        extra = {
            "fps": f"{fps_num}/{fps_den}",
            "bit_depth": settings.bit_depth,
            "audio_codec": "xHE-AAC" if has_audio else "none",
        }
        library.add_item(source=str(src), output=str(dest), extra=extra)
        log(f"Done → {dest}")
        return dest
    finally:
        if settings.keep_work:
            log(f"Work directory kept: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)
