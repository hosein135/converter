"""Build AV2 MP4 files that vlc-av2 can demux (av02 + av2C)."""

from __future__ import annotations

import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from av2converter.paths import which


class MuxError(RuntimeError):
    pass


def _be32(value: int) -> bytes:
    return struct.pack(">I", value & 0xFFFFFFFF)


def _be16(value: int) -> bytes:
    return struct.pack(">H", value & 0xFFFF)


def _box(kind: bytes, payload: bytes) -> bytes:
    return _be32(8 + len(payload)) + kind + payload


def _full_box(kind: bytes, version: int, flags: int, payload: bytes) -> bytes:
    return _box(kind, bytes([version, (flags >> 16) & 0xFF, (flags >> 8) & 0xFF, flags & 0xFF]) + payload)


def encode_leb128(value: int) -> bytes:
    if value < 0:
        raise MuxError("leb128 of negative value")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


@dataclass
class IvfFrame:
    pts: int
    payload: bytes


@dataclass
class IvfVideo:
    fourcc: bytes
    width: int
    height: int
    fps_num: int
    fps_den: int
    frames: list[IvfFrame] = field(default_factory=list)


def read_ivf(path: Path) -> IvfVideo:
    data = path.read_bytes()
    if len(data) < 32 or data[0:4] != b"DKIF":
        raise MuxError(f"Not an IVF file: {path}")
    fourcc = data[8:12]
    width, height = struct.unpack_from("<HH", data, 12)
    fps_num, fps_den = struct.unpack_from("<II", data, 16)
    frame_count = struct.unpack_from("<I", data, 24)[0]
    offset = 32
    frames: list[IvfFrame] = []
    while offset + 12 <= len(data):
        size, pts = struct.unpack_from("<IQ", data, offset)
        offset += 12
        payload = data[offset : offset + size]
        if len(payload) != size:
            break
        frames.append(IvfFrame(pts=pts, payload=payload))
        offset += size
        if frame_count and len(frames) >= frame_count:
            break
    if not frames:
        raise MuxError(f"IVF file has no frames: {path}")
    return IvfVideo(
        fourcc=fourcc,
        width=width or 1,
        height=height or 1,
        fps_num=fps_num or 30,
        fps_den=fps_den or 1,
        frames=frames,
    )


def iter_obus(buf: bytes) -> list[bytes]:
    """Split a length-delimited or in-band-size AV2/AV1-style OBU stream."""
    obus: list[bytes] = []
    i = 0
    n = len(buf)
    while i < n:
        start = i
        hdr = buf[i]
        i += 1
        extension = (hdr >> 2) & 1
        has_size = (hdr >> 1) & 1
        if extension:
            if i >= n:
                break
            i += 1
        if has_size:
            value = 0
            shift = 0
            while i < n:
                b = buf[i]
                i += 1
                value |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
                if shift > 28:
                    break
            payload = buf[i : i + value]
            i += len(payload)
            obus.append(buf[start:i])
        else:
            obus.append(buf[start:])
            break
    return obus or [buf]


def _obu_type(obu: bytes) -> int:
    if not obu:
        return -1
    return (obu[0] >> 3) & 0x0F


def config_obus_from_frame(payload: bytes) -> bytes:
    """
    Build the av2C configOBUs blob that vlc-av2 copies after the 9-byte header.

    dav2d wants length-prefixed config OBUs (sequence header, etc.).
    """
    packed = bytearray()
    for obu in iter_obus(payload):
        obu_type = _obu_type(obu)
        # AV1/AV2 sequence header is type 1; keep other non-frame config too.
        # Skip temporal delimiter (type 2) and frame/tile groups (typically 3, 6).
        if obu_type in (2, 3, 6):
            continue
        if obu_type == 1 or obu_type in (0, 4, 5):
            packed += encode_leb128(len(obu)) + obu
    if not packed:
        # Fall back to prefixing the whole first-frame payload.
        packed = encode_leb128(len(payload)) + payload
    return bytes(packed)


def av2c_box(config_obus: bytes, width: int, height: int) -> bytes:
    """9-byte AV2CodecConfigurationRecord used by vlc-av2 / av2-tools, plus configOBUs."""
    # Bit layout from av2-tools serialize():
    # version 8, profile 5, level 5, tier 1, chroma 3, bitdepth 3,
    # mono_out 1, still 1, film_grain 1, delay_present 1, delay 4,
    # reserved 7, max_w-1 16, max_h-1 16  => 9 bytes
    bits = []

    def write(value: int, n: int) -> None:
        bits.append((value, n))

    write(1, 8)  # configurationVersion
    write(0, 5)  # seq_profile_idc
    write(0, 5)  # seq_level_idx
    write(0, 1)  # seq_tier
    write(1, 3)  # chroma_format_idc (4:2:0)
    write(1, 3)  # bit_depth_idc (10-bit → 1 in some mappings; vlc skips this)
    write(0, 1)
    write(0, 1)
    write(0, 1)
    write(0, 1)
    write(0, 4)
    write(0, 7)
    write(max(width - 1, 0), 16)
    write(max(height - 1, 0), 16)
    acc = 0
    filled = 0
    out = bytearray()
    for value, n in bits:
        acc = (acc << n) | (value & ((1 << n) - 1))
        filled += n
        while filled >= 8:
            filled -= 8
            out.append((acc >> filled) & 0xFF)
            acc &= (1 << filled) - 1
    if len(out) != 9:
        out = bytearray(9)
    payload = bytes(out) + config_obus
    return _box(b"av2C", payload)


def write_av2_mp4(ivf: IvfVideo, dest: Path, timescale: int | None = None) -> None:
    fps_num = ivf.fps_num or 30
    fps_den = ivf.fps_den or 1
    ts = timescale or fps_num
    duration_per_frame = max(int(round(ts * fps_den / fps_num)), 1)
    sample_durations = [duration_per_frame] * len(ivf.frames)
    total_duration = duration_per_frame * len(ivf.frames)

    samples = [frame.payload for frame in ivf.frames]
    config = config_obus_from_frame(samples[0])
    av2c = av2c_box(config, ivf.width, ivf.height)

    # VisualSampleEntry('av02') + av2C
    visual = (
        bytes(6)
        + _be16(1)  # data_reference_index
        + bytes(16)
        + _be16(ivf.width)
        + _be16(ivf.height)
        + _be32(0x00480000)
        + _be32(0x00480000)
        + _be32(0)
        + _be16(1)
        + bytes(32)  # compressorname
        + _be16(0x0018)
        + struct.pack(">h", -1)
        + av2c
    )
    av02 = _box(b"av02", visual)
    stsd = _full_box(b"stsd", 0, 0, _be32(1) + av02)
    stts = _full_box(b"stts", 0, 0, _be32(1) + _be32(len(samples)) + _be32(duration_per_frame))
    stss_indices = [i + 1 for i, sample in enumerate(samples) if i == 0 or _looks_like_keyframe(sample)]
    if not stss_indices:
        stss_indices = [1]
    stss = _full_box(
        b"stss",
        0,
        0,
        _be32(len(stss_indices)) + b"".join(_be32(i) for i in stss_indices),
    )
    stsc = _full_box(b"stsc", 0, 0, _be32(1) + _be32(1) + _be32(len(samples)) + _be32(1))
    if any(len(s) > 0xFFFFFFFF for s in samples):
        raise MuxError("sample larger than 4 GiB")
    stsz = _full_box(
        b"stsz",
        0,
        0,
        _be32(0) + _be32(len(samples)) + b"".join(_be32(len(s)) for s in samples),
    )
    # Chunk offset filled after we know mdat position.
    stco_placeholder = _full_box(b"stco", 0, 0, _be32(1) + _be32(0))
    stbl = _box(b"stbl", stsd + stts + stss + stsc + stsz + stco_placeholder)
    url = _full_box(b"url ", 0, 1, b"")
    dref = _full_box(b"dref", 0, 0, _be32(1) + url)
    dinf = _box(b"dinf", dref)
    vmhd = _full_box(b"vmhd", 0, 1, _be16(0) + _be16(0) + _be16(0) + _be16(0))
    minf = _box(b"minf", vmhd + dinf + stbl)
    hdlr = _full_box(
        b"hdlr",
        0,
        0,
        b"\x00\x00\x00\x00" + b"vide" + bytes(12) + b"AV2 Video\x00",
    )
    mdhd = _full_box(
        b"mdhd",
        0,
        0,
        _be32(0)
        + _be32(0)
        + _be32(ts)
        + _be32(total_duration)
        + _be16(0x55C4)
        + _be16(0),
    )
    mdia = _box(b"mdia", mdhd + hdlr + minf)
    tkhd = _full_box(
        b"tkhd",
        0,
        0x3,
        _be32(0)
        + _be32(0)
        + _be32(1)
        + _be32(0)
        + _be32(total_duration)
        + bytes(8)
        + _be16(0)
        + _be16(0)
        + _be16(0)
        + _be16(0)
        + bytes(
            [
                0x00,
                0x01,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x01,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x40,
                0x00,
                0x00,
                0x00,
            ]
        )
        + _be32(ivf.width << 16)
        + _be32(ivf.height << 16),
    )
    trak = _box(b"trak", tkhd + mdia)
    mvhd = _full_box(
        b"mvhd",
        0,
        0,
        _be32(0)
        + _be32(0)
        + _be32(ts)
        + _be32(total_duration)
        + _be32(0x00010000)
        + _be16(0x0100)
        + _be16(0)
        + bytes(8)
        + bytes(
            [
                0x00,
                0x01,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x01,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x40,
                0x00,
                0x00,
                0x00,
            ]
        )
        + bytes(24)
        + _be32(2),
    )
    moov = _box(b"moov", mvhd + trak)
    mdat_payload = b"".join(samples)
    ftyp = _box(b"ftyp", b"isom" + _be32(0x200) + b"isomiso6av02mp41")

    # mdat comes after ftyp + moov so we can patch stco.
    mdat_header = 8 + (8 if len(mdat_payload) + 8 >= 0xFFFFFFFF else 0)
    mdat_offset = len(ftyp) + len(moov)
    # moov currently has stco=0; rebuild with the real offset.
    chunk_offset = mdat_offset + 8
    stco = _full_box(b"stco", 0, 0, _be32(1) + _be32(chunk_offset))
    stbl = _box(b"stbl", stsd + stts + stss + stsc + stsz + stco)
    minf = _box(b"minf", vmhd + dinf + stbl)
    mdia = _box(b"mdia", mdhd + hdlr + minf)
    trak = _box(b"trak", tkhd + mdia)
    moov = _box(b"moov", mvhd + trak)
    chunk_offset = len(ftyp) + len(moov) + 8
    stco = _full_box(b"stco", 0, 0, _be32(1) + _be32(chunk_offset))
    stbl = _box(b"stbl", stsd + stts + stss + stsc + stsz + stco)
    minf = _box(b"minf", vmhd + dinf + stbl)
    mdia = _box(b"mdia", mdhd + hdlr + minf)
    trak = _box(b"trak", tkhd + mdia)
    moov = _box(b"moov", mvhd + trak)
    mdat = _box(b"mdat", mdat_payload)
    dest.write_bytes(ftyp + moov + mdat)
    _ = sample_durations, mdat_header  # keep names for readability


def _looks_like_keyframe(payload: bytes) -> bool:
    for obu in iter_obus(payload):
        if _obu_type(obu) == 1:
            return True
    return False


def ivf_to_av2_mp4(ivf_path: Path, dest: Path) -> None:
    ivf = read_ivf(ivf_path)
    write_av2_mp4(ivf, dest)


def merge_audio(video_mp4: Path, audio_m4a: Path, dest: Path) -> None:
    """Attach an xHE-AAC M4A track to an AV2 MP4, preserving the video sample entry."""
    mp4box = which("MP4Box")
    if mp4box:
        cmd = [
            mp4box,
            "-add",
            str(video_mp4),
            "-add",
            str(audio_m4a),
            "-new",
            str(dest),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 0:
            return
    ffmpeg = which("ffmpeg")
    if not ffmpeg:
        raise MuxError("Need MP4Box (gpac) or ffmpeg to mux xHE-AAC with AV2")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_mp4),
        "-i",
        str(audio_m4a),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c",
        "copy",
        "-tag:v",
        "av02",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not dest.is_file():
        raise MuxError(
            "Could not mux AV2 video with xHE-AAC audio.\n"
            + (proc.stderr or proc.stdout or "")
        )
