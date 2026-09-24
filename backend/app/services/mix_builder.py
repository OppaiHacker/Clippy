from typing import Dict, Any, List, Tuple
from pathlib import Path

def export_window(mix_doc: Dict[str, Any], total_clip_duration: float) -> Tuple[float, float]:
    """(start, end) of the export in source seconds, from the trim or the whole clip."""
    trim = mix_doc.get("trim") if isinstance(mix_doc.get("trim"), dict) else {}
    t0 = max(0.0, float(trim.get("start") or 0.0))
    t1 = float(trim.get("end") or total_clip_duration)
    return t0, max(t0, t1)

def build_ffmpeg_export_command(
    clip_path: Path,
    imported_tracks: List[Dict[str, Any]],  # [{id, path, ...}]
    mix_doc: Dict[str, Any],
    preset: str,
    output_path: Path,
    discord_limit_mb: float = 25.0,
    total_clip_duration: float = 0.0
) -> List[str]:
    """
    Builds the ffmpeg command with audio and video filters from the mix document.
    REMEMBER: normalize=0 on amix is mandatory!
    """
    cmd = ["ffmpeg", "-v", "error", "-y"]

    # Input 0: the main video clip
    cmd.extend(["-i", str(clip_path)])

    # Extra inputs for imported tracks
    # track_input_map: (import_id or stream_index) -> (ffmpeg_input_idx, stream_idx)
    input_index_map = {}
    current_input_idx = 1
    for imp in imported_tracks:
        cmd.extend(["-i", str(imp["source_path"])])
        input_index_map[f"import_{imp['id']}"] = current_input_idx
        current_input_idx += 1

    inputs = cmd[4:]  # -i clip + -i imports; audio_only builds its own command from them

    trim = mix_doc.get("trim")
    speed = float(mix_doc.get("speed", 1.0))
    if speed <= 0:
        speed = 1.0
    # export window in source time - fades are measured from it
    t0, t1 = export_window(mix_doc, total_clip_duration)
    video_fade = mix_doc.get("video_fade", {})
    crop = mix_doc.get("crop")
    master = mix_doc.get("master", {})
    tracks = mix_doc.get("tracks", [])

    # Audio filters
    audio_filter_chains = []
    mixed_labels = []
    label_counter = 0

    # solo works like in the preview: if any track is soloed, only soloed tracks play
    any_solo = any(t.get("solo") for t in tracks)

    for trk in tracks:
        if trk.get("mute", False):
            continue
        if any_solo and not trk.get("solo"):
            continue

        gain = float(trk.get("gain", 1.0))
        if gain <= 0.0001:
            continue

        # Pick the input
        if "stream_index" in trk:
            # Input 0:a:X
            s_idx = trk["stream_index"]
            in_label = f"0:{s_idx}"
        elif "import_id" in trk:
            imp_key = f"import_{trk['import_id']}"
            if imp_key not in input_index_map:
                continue
            in_label = f"{input_index_map[imp_key]}:a:0"
        else:
            continue

        # the mic is often mono: force one layout so pan and amix behave
        filters = ["aformat=channel_layouts=stereo"]

        # Offset: positive delays the track, negative advances it (cuts its start)
        offset_s = float(trk.get("offset", 0.0))
        if offset_s > 0:
            filters.append(f"adelay=delays={int(offset_s * 1000)}:all=1")
        elif offset_s < 0:
            filters.append(f"atrim=start={-offset_s:.3f},asetpts=PTS-STARTPTS")

        # Fade in / out at the edges of the exported range
        fade_in = float(trk.get("fade_in", 0.0))
        fade_out = float(trk.get("fade_out", 0.0))
        if fade_in > 0:
            filters.append(f"afade=t=in:st={t0:.3f}:d={fade_in}")
        if fade_out > 0 and t1 - t0 > fade_out:
            filters.append(f"afade=t=out:st={t1 - fade_out:.3f}:d={fade_out}")

        # Volume
        if abs(gain - 1.0) > 0.001:
            filters.append(f"volume={gain:.3f}")

        # Pan
        pan = float(trk.get("pan", 0.0))
        if abs(pan) > 0.01:
            # pan=-1 => left, pan=1 => right
            # stereo to stereo pan: c0=...|c1=...
            # Left gain: (1 - pan)/2 * 2?
            # Standard pan: left=(1-pan), right=(1+pan)
            l_gain = max(0.0, min(1.0, 1.0 - pan))
            r_gain = max(0.0, min(1.0, 1.0 + pan))
            filters.append(f"pan=stereo|c0={l_gain:.2f}*c0|c1={r_gain:.2f}*c1")

        # Effects
        for eff in trk.get("effects", []):
            etype = eff.get("type")
            if etype == "highpass":
                freq = eff.get("freq", 80)
                filters.append(f"highpass=f={freq}")
            elif etype == "lowpass":
                freq = eff.get("freq", 12000)
                filters.append(f"lowpass=f={freq}")
            elif etype == "compressor":
                th = eff.get("threshold", -18)
                ratio = eff.get("ratio", 3)
                filters.append(f"acompressor=threshold={th}dB:ratio={ratio}")
            elif etype == "gate":
                th = eff.get("threshold", -40)
                filters.append(f"agate=threshold={th}dB")

        out_label = f"a{label_counter}"
        label_counter += 1

        audio_filter_chains.append(f"[{in_label}]" + ",".join(filters) + f"[{out_label}]")
        mixed_labels.append(f"[{out_label}]")

    # Amix
    if not mixed_labels:
        # Complete silence
        audio_filter_chains.append("anullsrc=channel_layout=stereo:sample_rate=48000[mix]")
    elif len(mixed_labels) == 1:
        # One track - no amix needed
        audio_filter_chains.append(f"{mixed_labels[0]}anull[mix]")
    else:
        # normalize=0 is MANDATORY
        inputs_cnt = len(mixed_labels)
        audio_filter_chains.append(
            "".join(mixed_labels) + f"amix=inputs={inputs_cnt}:normalize=0[mix]"
        )

    # Master limiter / normalization
    master_gain = float(master.get("gain", 1.0))
    master_filters = []
    if abs(master_gain - 1.0) > 0.001:
        master_filters.append(f"volume={master_gain:.3f}")
    if master.get("limiter", True):
        master_filters.append("alimiter=limit=0.95")
    if master.get("normalize_lufs"):
        lufs = master.get("normalize_lufs")
        master_filters.append(f"loudnorm=I={lufs}:TP=-1.5")

    if master_filters:
        audio_filter_chains.append("[mix]" + ",".join(master_filters) + "[final_audio]")
        final_audio_label = "[final_audio]"
    else:
        final_audio_label = "[mix]"

    # Video filters (speed, fade, crop)
    video_filters = []
    v_fade_in = float(video_fade.get("in", 0.0))
    v_fade_out = float(video_fade.get("out", 0.0))
    if v_fade_in > 0:
        video_filters.append(f"fade=t=in:st={t0:.3f}:d={v_fade_in}")
    if v_fade_out > 0 and t1 - t0 > v_fade_out:
        video_filters.append(f"fade=t=out:st={t1 - v_fade_out:.3f}:d={v_fade_out}")

    if speed != 1.0:
        video_filters.append(f"setpts=PTS/{speed}")
        # Audio speed
        if 0.5 <= speed <= 2.0:
            audio_filter_chains.append(f"{final_audio_label}atempo={speed}[spd_audio]")
            final_audio_label = "[spd_audio]"
        elif speed > 2.0:
            audio_filter_chains.append(f"{final_audio_label}atempo=2.0,atempo={speed/2.0:.2f}[spd_audio]")
            final_audio_label = "[spd_audio]"
        elif speed < 0.5:
            audio_filter_chains.append(f"{final_audio_label}atempo=0.5,atempo={speed/0.5:.2f}[spd_audio]")
            final_audio_label = "[spd_audio]"

    has_crop = False
    if crop and isinstance(crop, dict):
        cw = crop.get("w")
        ch = crop.get("h")
        cx = crop.get("x", 0)
        cy = crop.get("y", 0)
        if cw and ch:
            video_filters.append(f"crop={cw}:{ch}:{cx}:{cy}")
            has_crop = True

    if preset == "vertical":
        if not has_crop:
            video_filters.append("crop=ih*9/16:ih")
        video_filters.append("scale=1080:1920")

    if video_filters:
        video_chain = "[0:v]" + ",".join(video_filters) + "[final_video]"
        final_video_label = "[final_video]"
    else:
        video_chain = "[0:v]copy[final_video]"
        final_video_label = "0:v"

    # Assemble filter_complex
    filter_complex_parts = []
    if video_filters:
        filter_complex_parts.append(video_chain)
    filter_complex_parts.extend(audio_filter_chains)

    filter_complex_str = ";".join(filter_complex_parts)

    cmd.extend(["-filter_complex", filter_complex_str])

    # Trim in/out: -ss/-to come after the filters, so they are in output time (after the speed change)
    trim_mode = trim.get("mode", "accurate") if isinstance(trim, dict) else "accurate"
    trim_args = []
    if isinstance(trim, dict):
        if t0 > 0:
            trim_args += ["-ss", f"{t0 / speed:.3f}"]
        if trim.get("end"):
            trim_args += ["-to", f"{t1 / speed:.3f}"]
    cmd.extend(trim_args)

    # Output encoding based on preset
    cmd.extend(["-map", final_video_label, "-map", final_audio_label])

    if preset == "audio_only":
        # Mix to opus
        cmd = ["ffmpeg", "-v", "error", "-y", *inputs]
        cmd.extend(["-filter_complex", ";".join(audio_filter_chains), *trim_args])
        cmd.extend(["-map", final_audio_label, "-c:a", "libopus", "-b:a", "192k", str(output_path)])
        return cmd

    if preset == "discord":
        # Target size limit e.g. 25MB
        calc_dur = max(1.0, (t1 - t0) / speed)

        total_bits = discord_limit_mb * 8 * 1024 * 1024 * 0.95  # 5% safety margin
        audio_bitrate_k = 128
        total_bitrate_k = total_bits / calc_dur / 1000
        video_bitrate_k = max(200, int(total_bitrate_k - audio_bitrate_k))

        cmd.extend([
            "-c:v", "h264_nvenc",
            "-b:v", f"{video_bitrate_k}k",
            "-maxrate", f"{int(video_bitrate_k * 1.2)}k",
            "-bufsize", f"{int(video_bitrate_k * 2)}k",
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate_k}k",
            str(output_path)
        ])
    elif preset == "youtube":
        cmd.extend([
            "-c:v", "h264_nvenc",
            "-preset", "p5",
            "-cq", "17",
            "-c:a", "aac",
            "-b:a", "320k",
            str(output_path)
        ])
    elif preset == "vertical":
        # 9:16 vertical crop/scale
        cmd.extend([
            "-c:v", "h264_nvenc",
            "-preset", "p5",
            "-cq", "19",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path)
        ])
    else:  # original / default
        # nothing to cut (no trim) or a keyframe cut was asked for: copy the video stream
        if not video_filters and (trim_mode == "fast" or not trim_args):
            cmd.extend([
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path)
            ])
        else:
            # Frame-accurate via NVENC
            cmd.extend([
                "-c:v", "h264_nvenc",
                "-preset", "p5",
                "-cq", "19",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path)
            ])

    return cmd
