import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def render_preview(directory: Path) -> None:
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    shape = tuple(metadata["shape"])
    state = np.memmap(directory / metadata["state_file"], mode="r", dtype="<f2", shape=shape)
    disp = np.memmap(directory / metadata["displacement_file"], mode="r", dtype="<f2", shape=shape)
    font = ImageFont.load_default()
    frames = []
    side = 384
    minimum = metadata["displacement_min_m"][2]
    span = metadata["displacement_max_m"][2] - minimum
    max_abs_w = max(abs(minimum), abs(minimum + span), 1e-12)
    for index, time in enumerate(metadata["times_seconds"]):
        damage = np.asarray(state[index, :, :, 0], dtype=float)[::-1]
        coverage = np.asarray(disp[index, :, :, 3], dtype=float)[::-1]
        w = (np.asarray(disp[index, :, :, 2], dtype=float) * span + minimum)[::-1] * coverage
        crack = np.empty((*damage.shape, 3))
        crack[:] = (13, 25, 38)
        crack += damage[:, :, None] * np.array([225, 217, 208])
        normalized_w = np.clip(w / max_abs_w, -1, 1)
        warp = np.zeros_like(crack)
        warp[:] = (30, 40, 50)
        warp += np.maximum(-normalized_w, 0)[:, :, None] * np.array([10, 100, 195])
        warp += np.maximum(normalized_w, 0)[:, :, None] * np.array([210, 90, 20])
        left = Image.fromarray(np.uint8(np.clip(crack, 0, 255))).resize((side, side))
        right = Image.fromarray(np.uint8(np.clip(warp, 0, 255))).resize((side, side))
        frame = Image.new("RGB", (side * 2 + 36, side + 106), (245, 247, 250))
        frame.paste(left, (12, 64))
        frame.paste(right, (side + 24, 64))
        draw = ImageDraw.Draw(frame)
        kind = metadata["source_kind"].upper()
        title = f"{kind} | Glass impact field playback"
        draw.text((12, 10), title, fill=(15, 30, 50), font=font)
        note = "ARTIFICIAL PATTERN - not a COMSOL fracture result" if kind == "SYNTHETIC" else "Imported fields - physics validation status in metadata"
        draw.text((12, 29), note, fill=(170, 45, 25), font=font)
        draw.text((12, 48), "Damage d: black=0, white=1 | +Y up, +X right", fill=(25, 40, 55), font=font)
        draw.text((side + 24, 48), "Local W: blue=-Z, orange=+Z | fixed scale", fill=(25, 40, 55), font=font)
        draw.text((12, side + 73), f"t={time * 1000:6.3f} ms   frame {index + 1}/{shape[0]}   max d={damage.max():.3f}", fill=(25, 40, 55), font=font)
        draw.text((side + 24, side + 73), f"w=[{w.min()*1000:.3f}, {w.max()*1000:.3f}] mm | scale +/-{max_abs_w*1000:.3f} mm", fill=(25, 40, 55), font=font)
        draw.text((12, side + 89), f"Shown over {metadata['preview']['display_duration_seconds']:.1f} s; physics duration {metadata['duration_seconds']:.5f} s", fill=(80, 90, 105), font=font)
        frames.append(frame)
    times = np.asarray(metadata["times_seconds"])
    intervals = np.append(np.diff(times), np.diff(times)[-1])
    durations = np.maximum(20, np.rint(intervals / intervals.sum() * metadata["preview"]["display_duration_seconds"] * 1000)).astype(int)
    frames[0].save(directory / "preview.gif", save_all=True, append_images=frames[1:], duration=durations.tolist(), loop=0, disposal=2)
    frames[-1].save(directory / "preview_final.png")
    chosen = [0, len(frames) // 3, 2 * len(frames) // 3, len(frames) - 1]
    small_size = (frames[0].width // 2, frames[0].height // 2)
    montage = Image.new("RGB", (small_size[0] * 2, small_size[1] * 2))
    for n, frame_index in enumerate(chosen):
        montage.paste(frames[frame_index].resize(small_size), ((n % 2) * small_size[0], (n // 2) * small_size[1]))
    montage.save(directory / "preview_montage.png")
