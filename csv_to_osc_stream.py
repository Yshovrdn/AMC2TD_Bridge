#!/usr/bin/env python3

import argparse
import csv
import socket
import struct
import time
from pathlib import Path


def clean_path_text(text: str) -> str:
    return text.strip().strip('"').strip("'")


def pad_osc_string(text: str) -> bytes:
    encoded = text.encode("utf-8") + b"\x00"
    padding = (4 - (len(encoded) % 4)) % 4
    return encoded + (b"\x00" * padding)


def encode_osc_message(address: str, values):
    type_tags = [","]
    encoded_values = []

    for value in values:
        if isinstance(value, int):
            type_tags.append("i")
            encoded_values.append(struct.pack(">i", value))
        elif isinstance(value, float):
            type_tags.append("f")
            encoded_values.append(struct.pack(">f", value))
        elif isinstance(value, str):
            type_tags.append("s")
            encoded_values.append(pad_osc_string(value))
        else:
            raise TypeError(f"Unsupported OSC value type: {type(value)!r}")

    return b"".join(
        [
            pad_osc_string(address),
            pad_osc_string("".join(type_tags)),
            *encoded_values,
        ]
    )


def encode_osc_bundle(messages):
    bundle = [pad_osc_string("#bundle"), struct.pack(">Q", 1)]
    for message in messages:
        bundle.append(struct.pack(">i", len(message)))
        bundle.append(message)
    return b"".join(bundle)


def encode_point_axis_messages(prefix: str, point_name: str, xyz_values):
    return [
        encode_osc_message(f"{prefix}/{point_name}_x", [float(xyz_values[0])]),
        encode_osc_message(f"{prefix}/{point_name}_y", [float(xyz_values[1])]),
        encode_osc_message(f"{prefix}/{point_name}_z", [float(xyz_values[2])]),
    ]


def infer_point_columns(headers):
    groups = {}

    for index, header in enumerate(headers):
        clean_header = header.strip()
        lower_header = clean_header.lower()

        for suffix, axis in (("_x", "x"), ("_y", "y"), ("_z", "z")):
            if lower_header.endswith(suffix) and len(clean_header) > len(suffix):
                base_name = clean_header[: -len(suffix)]
                groups.setdefault(base_name, {"indices": {}, "first_index": index})
                groups[base_name]["indices"][axis] = index
                groups[base_name]["first_index"] = min(groups[base_name]["first_index"], index)
                break

    return [
        {"name": name, **group}
        for name, group in sorted(groups.items(), key=lambda item: item[1]["first_index"])
        if all(axis in group["indices"] for axis in ("x", "y", "z"))
    ]


def load_point_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)

    if len(rows) < 2:
        raise ValueError(f"{path} must contain a header row and at least one data row.")

    headers = rows[0]
    point_columns = infer_point_columns(headers)
    frame_index = next(
        (index for index, header in enumerate(headers) if header.strip().lower() == "frame"),
        None,
    )

    if not point_columns:
        raise ValueError(
            f"{path} does not contain XYZ point columns like joint_x, joint_y, joint_z."
        )

    frames = []
    for row_number, row in enumerate(rows[1:], start=1):
        frame_id = row[frame_index].strip() if frame_index is not None and frame_index < len(row) else str(row_number)
        points = []

        for point_column in point_columns:
            values = []
            valid = True

            for axis in ("x", "y", "z"):
                value_index = point_column["indices"][axis]
                try:
                    value_text = row[value_index].strip()
                except IndexError:
                    value_text = ""

                if value_text == "":
                    valid = False
                    break

                try:
                    values.append(float(value_text))
                except ValueError:
                    valid = False
                    break

            if valid:
                points.append({"name": point_column["name"], "xyz": values})

        frames.append({"frame": frame_id, "points": points})

    return frames, [point_column["name"] for point_column in point_columns]


def stream_csv_over_osc(
    csv_path: Path,
    host: str,
    port: int,
    fps: float,
    loop: bool,
    prefix: str,
    max_frames: int | None,
):
    frames, point_names = load_point_csv(csv_path)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (host, port)

    metadata_messages = [
        encode_osc_message(f"{prefix}/meta/point_count", [len(point_names)]),
        encode_osc_message(f"{prefix}/meta/frame_count", [len(frames)]),
    ]
    sock.sendto(encode_osc_bundle(metadata_messages), target)

    frame_duration = 1.0 / fps if fps > 0 else 0.0
    sent_frames = 0

    try:
        while True:
            for frame_index, frame in enumerate(frames):
                start_time = time.perf_counter()
                messages = [
                    encode_osc_message(f"{prefix}/frame_index", [frame_index]),
                    encode_osc_message(f"{prefix}/frame", [int(frame["frame"])] if str(frame["frame"]).isdigit() else [str(frame["frame"])]),
                ]

                for point in frame["points"]:
                    messages.extend(
                        encode_point_axis_messages(prefix, point["name"], point["xyz"])
                    )

                sock.sendto(encode_osc_bundle(messages), target)
                sent_frames += 1

                if max_frames is not None and sent_frames >= max_frames:
                    return len(frames), len(point_names), sent_frames

                if frame_duration > 0:
                    remaining = frame_duration - (time.perf_counter() - start_time)
                    if remaining > 0:
                        time.sleep(remaining)

            if not loop:
                return len(frames), len(point_names), sent_frames
    finally:
        sock.close()


def prompt_for_values():
    csv_text = input("Drag the XYZ CSV file here, then press Enter: ").strip()
    if not csv_text:
        raise ValueError("No CSV file was provided.")

    host_text = input("TouchDesigner host [127.0.0.1]: ").strip() or "127.0.0.1"
    port_text = input("TouchDesigner OSC port [7000]: ").strip() or "7000"
    fps_text = input("Playback FPS [30]: ").strip() or "30"
    loop_text = input("Loop playback? [Y/n]: ").strip().lower()

    return (
        Path(clean_path_text(csv_text)).expanduser().resolve(),
        host_text,
        int(port_text),
        float(fps_text),
        loop_text not in {"n", "no"},
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Stream an XYZ point CSV to TouchDesigner over OSC on the same laptop."
    )
    parser.add_argument("csv_path", nargs="?", type=Path, help="Path to the XYZ CSV file")
    parser.add_argument("--host", default="127.0.0.1", help="Destination host")
    parser.add_argument("--port", type=int, default=7000, help="Destination UDP port")
    parser.add_argument("--fps", type=float, default=30.0, help="Playback rate in frames per second")
    parser.add_argument("--prefix", default="/mocap", help="OSC address prefix")
    parser.add_argument("--no-loop", action="store_true", help="Send the CSV once instead of looping")
    parser.add_argument("--max-frames", type=int, help="Optional cap for test runs")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.csv_path is None:
        csv_path, host, port, fps, loop = prompt_for_values()
        prefix = args.prefix
        max_frames = args.max_frames
    else:
        csv_path = args.csv_path.expanduser().resolve()
        host = args.host
        port = args.port
        fps = args.fps
        loop = not args.no_loop
        prefix = args.prefix
        max_frames = args.max_frames

    frame_count, point_count, sent_frames = stream_csv_over_osc(
        csv_path=csv_path,
        host=host,
        port=port,
        fps=fps,
        loop=loop,
        prefix=prefix.rstrip("/") or "/mocap",
        max_frames=max_frames,
    )

    print(
        f"Streamed {sent_frames} frames from {csv_path.name} with {point_count} points to {host}:{port}"
        f" using prefix {prefix.rstrip('/') or '/mocap'}"
    )
    if loop and max_frames is None:
        print("Loop mode was enabled; the stream stopped only because the process ended.")
    else:
        print(f"Source CSV contained {frame_count} frames.")


if __name__ == "__main__":
    main()
