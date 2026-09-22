from __future__ import annotations

import json
import os
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
    cpu_used: int = 9
    cq_level: int = 32
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


def _hwaccel(ffmpeg: str) -> str | None:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-hwaccels"],
        capture_output=True,
        text=True,
    )
    names = {line.strip() for line in (proc.stdout or "").splitlines()}
    if "cuda" in names:
        return "cuda"
    if "nvdec" in names:
        return "nvdec"
    return None


def _gpu_pix_fmt(bit_depth: int, pix: str) -> str:
    if bit_depth <= 8:
        return "yuv420p" if "422" not in pix and "444" not in pix else pix
    if bit_depth == 10 and "444" not in pix and "422" not in pix:
        return "yuv420p10le"
    return pix


def _bit_depth(stream: dict | None) -> int:
    """Bit depth of the source picture. The encode keeps this instead of upconverting."""
    if not stream:
        return 8
    raw = stream.get("bits_per_raw_sample")
    try:
        bits = int(raw or 0)
    except (TypeError, ValueError):
        bits = 0
    if bits > 0:
        return bits
    pix = str(stream.get("pix_fmt") or "")
    if "12" in pix:
        return 12
    if "10" in pix:
        return 10
    return 8


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
    bit_depth = _bit_depth(video)
    try:
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
    except (TypeError, ValueError):
        width, height = 0, 0
    pix = str(video.get("pix_fmt") or "yuv420p")
    dest = Path(output).expanduser() if output else converted_dir() / f"{src.stem}.av2.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="av2converter-"))
    try:
        y4m = work / "video.y4m"
        wav = work / "audio.wav"
        ivf = work / "video.ivf"
        obu = work / "video.obu"
        audio_m4a = work / "audio.m4a"
        video_mp4 = work / "video.mp4"

        log(
            f"Keeping source video: {width}x{height}, {fps_num}/{fps_den} fps, "
            f"{bit_depth}-bit {pix}. Only the codec changes."
        )
        accel = None if os.environ.get("AV2_CPU_ONLY") == "1" else _hwaccel(ffmpeg)
        decode_video = [ffmpeg, "-y"]
        if accel:
            log(f"Decoding on the NVIDIA GPU ({accel}) into Y4M…")
            decode_video += ["-hwaccel", accel, "-hwaccel_output_format", "cuda", "-i", str(src), "-an"]
            decode_video += ["-vf", f"hwdownload,format={_gpu_pix_fmt(bit_depth, pix)}"]
        else:
            log("Decoding video to Y4M for the AV2 reference encoder…")
            decode_video += ["-i", str(src), "-an"]
        decode_video += ["-fps_mode", "passthrough"]
        if bit_depth > 8:
            decode_video += ["-strict", "unofficial"]
        decode_video += [str(y4m)]
        try:
            _run(decode_video, log)
        except ConvertError:
            if not accel:
                raise
            log("GPU decode failed. Decoding on the CPU instead.")
            decode_video = [ffmpeg, "-y", "-i", str(src), "-an", "-fps_mode", "passthrough"]
            if bit_depth > 8:
                decode_video += ["-strict", "unofficial"]
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

        threads = max(1, os.cpu_count() or 1)
        # Picture size, frame rate, and bit depth stay as probed. These flags
        # only cut the reference encoder's search so a short clip can finish.
        tile_columns = 2 if threads >= 4 else 1 if threads >= 2 else 0
        log(
            f"Encoding AV2 with AVM avmenc (cpu-used={settings.cpu_used}, "
            f"cq={settings.cq_level}, threads={threads}). "
            "The first frame is the slow one; later frames print a POC line each."
        )
        encode = [
            avmenc,
            f"--cpu-used={settings.cpu_used}",
            f"--threads={threads}",
            "--row-mt=1",
            "--lag-in-frames=0",
            "--auto-alt-ref=0",
            "--enable-tpl-model=0",
            "--enable-keyframe-filtering=0",
            "--use-ml-erp-pruning=0",
            "--min-partition-size=16",
            "--reduced-tx-part-set=1",
            "--end-usage=q",
            f"--cq-level={settings.cq_level}",
            f"--bit-depth={bit_depth}",
            f"--fps={fps_num}/{fps_den}",
        ]
        if tile_columns:
            encode.append(f"--tile-columns={tile_columns}")
        encode += ["-o", str(ivf), str(y4m)]
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
            "bit_depth": bit_depth,
            "width": width,
            "height": height,
            "pix_fmt": pix,
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
