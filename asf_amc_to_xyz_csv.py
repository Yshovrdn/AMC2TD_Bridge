#!/usr/bin/env python3

import argparse
import csv
import math
from pathlib import Path


AXIS_NAMES = ("x", "y", "z")


def clean_path_text(text: str) -> str:
    return text.strip().strip('"').strip("'")


def default_output_path(amc_path: Path) -> Path:
    name = amc_path.name

    if name.lower().endswith(".amc.txt"):
        return amc_path.with_name(name[:-8] + "_xyz.csv")

    if amc_path.suffix.lower() in {".txt", ".amc"}:
        return amc_path.with_suffix(".csv").with_name(amc_path.stem + "_xyz.csv")

    return amc_path.with_name(amc_path.name + "_xyz.csv")


def identity_matrix():
    return [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]


def matrix_multiply(left, right):
    return [
        [
            sum(left[row][index] * right[index][column] for index in range(3))
            for column in range(3)
        ]
        for row in range(3)
    ]


def matrix_transpose(matrix):
    return [[matrix[column][row] for column in range(3)] for row in range(3)]


def apply_matrix(matrix, vector):
    return [
        sum(matrix[row][column] * vector[column] for column in range(3))
        for row in range(3)
    ]


def vector_add(left, right):
    return [left[index] + right[index] for index in range(3)]


def vector_scale(vector, scale):
    return [component * scale for component in vector]


def rotation_matrix(axis_name: str, angle_degrees: float):
    angle = math.radians(angle_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)

    if axis_name == "x":
        return [
            [1.0, 0.0, 0.0],
            [0.0, cosine, -sine],
            [0.0, sine, cosine],
        ]

    if axis_name == "y":
        return [
            [cosine, 0.0, sine],
            [0.0, 1.0, 0.0],
            [-sine, 0.0, cosine],
        ]

    if axis_name == "z":
        return [
            [cosine, -sine, 0.0],
            [sine, cosine, 0.0],
            [0.0, 0.0, 1.0],
        ]

    raise ValueError(f"Unsupported rotation axis {axis_name}")


def compose_rotations(angle_map, order):
    matrix = identity_matrix()
    for axis_name in order.lower():
        matrix = matrix_multiply(matrix, rotation_matrix(axis_name, angle_map.get(axis_name, 0.0)))
    return matrix


def compose_channel_rotation(channel_values, channel_order):
    matrix = identity_matrix()
    for channel_name in channel_order:
        lower = channel_name.lower()
        if lower in {"rx", "ry", "rz"}:
            matrix = matrix_multiply(matrix, rotation_matrix(lower[1], channel_values.get(lower, 0.0)))
    return matrix


def normalize_vector(vector):
    magnitude = math.sqrt(sum(component * component for component in vector))
    if magnitude == 0:
        return [0.0, 0.0, 0.0]
    return [component / magnitude for component in vector]


def parse_limits(lines, index, dof_count):
    limits = []
    while len(limits) < dof_count and index < len(lines):
      line = lines[index].strip()
      if not line:
          index += 1
          continue
      if line.startswith("("):
          limits.append(line)
          index += 1
          continue
      break
    return limits, index


def parse_asf(path: Path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    skeleton = {
        "root": {
            "position": [0.0, 0.0, 0.0],
            "orientation": [0.0, 0.0, 0.0],
            "rotation_order": "xyz",
            "channel_order": ["tx", "ty", "tz", "rx", "ry", "rz"],
        },
        "bones": {},
        "children": {"root": []},
        "bone_order": [],
    }

    section = None
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        index += 1

        if not line or line.startswith("#"):
            continue

        if line.startswith(":"):
            section = line.lower()
            continue

        if section == ":root":
            parts = line.split()
            keyword = parts[0].lower()
            if keyword == "order":
                skeleton["root"]["channel_order"] = [token.lower() for token in parts[1:]]
            elif keyword == "axis":
                skeleton["root"]["rotation_order"] = parts[1].lower()
            elif keyword == "position":
                skeleton["root"]["position"] = [float(value) for value in parts[1:4]]
            elif keyword == "orientation":
                skeleton["root"]["orientation"] = [float(value) for value in parts[1:4]]
            continue

        if section == ":bonedata" and line.lower() == "begin":
            bone = {
                "id": None,
                "name": None,
                "direction": [0.0, 0.0, 0.0],
                "length": 0.0,
                "axis_angles": [0.0, 0.0, 0.0],
                "axis_order": "xyz",
                "dof": [],
                "limits": [],
            }

            while index < len(lines):
                inner = lines[index].strip()
                index += 1

                if not inner:
                    continue

                if inner.lower() == "end":
                    break

                parts = inner.split()
                keyword = parts[0].lower()

                if keyword == "id":
                    bone["id"] = int(parts[1])
                elif keyword == "name":
                    bone["name"] = parts[1]
                elif keyword == "direction":
                    bone["direction"] = normalize_vector([float(value) for value in parts[1:4]])
                elif keyword == "length":
                    bone["length"] = float(parts[1])
                elif keyword == "axis":
                    bone["axis_angles"] = [float(value) for value in parts[1:4]]
                    bone["axis_order"] = parts[4].lower()
                elif keyword == "dof":
                    bone["dof"] = [token.lower() for token in parts[1:]]
                elif keyword == "limits":
                    limits, index = parse_limits(lines, index, len(bone["dof"]))
                    bone["limits"] = limits

            if bone["name"] is None:
                raise ValueError(f"Encountered an unnamed bone in {path}")

            bone["axis_matrix"] = compose_rotations(
                dict(zip(AXIS_NAMES, bone["axis_angles"])),
                bone["axis_order"],
            )
            bone["axis_inverse"] = matrix_transpose(bone["axis_matrix"])

            skeleton["bones"][bone["name"]] = bone
            skeleton["bone_order"].append(bone["name"])
            skeleton["children"].setdefault(bone["name"], [])
            continue

        if section == ":hierarchy" and line.lower() == "begin":
            while index < len(lines):
                inner = lines[index].strip()
                index += 1

                if not inner:
                    continue

                if inner.lower() == "end":
                    break

                parts = inner.split()
                parent = parts[0]
                children = parts[1:]
                skeleton["children"].setdefault(parent, [])
                skeleton["children"][parent].extend(children)
                for child in children:
                    skeleton["children"].setdefault(child, [])
            continue

    return skeleton


def parse_amc(path: Path):
    frames = []
    current_frame_number = None
    current_channels = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()

            if not line or line.startswith("#!") or line.startswith(":"):
                continue

            if line.isdigit():
                if current_channels is not None:
                    frames.append((current_frame_number, current_channels))
                current_frame_number = int(line)
                current_channels = {}
                continue

            if current_channels is None:
                continue

            parts = line.split()
            if len(parts) < 2:
                raise ValueError(f"Malformed motion line at {path}:{line_number}: {raw_line.rstrip()}")

            current_channels[parts[0]] = [float(value) for value in parts[1:]]

    if current_channels is not None:
        frames.append((current_frame_number, current_channels))

    if not frames:
        raise ValueError(f"No frame data found in {path}")

    return frames


def root_rotation_matrix(root_frame_values, skeleton):
    rotation_values = {}
    translation = skeleton["root"]["position"][:]

    for channel_name, value in zip(skeleton["root"]["channel_order"], root_frame_values):
        if channel_name in {"tx", "ty", "tz"}:
            translation[AXIS_NAMES.index(channel_name[1])] = value
        elif channel_name in {"rx", "ry", "rz"}:
            rotation_values[channel_name[1]] = value

    orientation_matrix = compose_rotations(
        dict(zip(AXIS_NAMES, skeleton["root"]["orientation"])),
        skeleton["root"]["rotation_order"],
    )
    motion_matrix = compose_channel_rotation(rotation_values, skeleton["root"]["channel_order"])
    return translation, matrix_multiply(orientation_matrix, motion_matrix)


def bone_rotation_matrix(bone, frame_values):
    channel_values = {}
    length_scale = 1.0

    for channel_name, value in zip(bone["dof"], frame_values):
        if channel_name in {"rx", "ry", "rz"}:
            channel_values[channel_name] = value
        elif channel_name == "l":
            length_scale = value

    motion_matrix = compose_channel_rotation(channel_values, bone["dof"])
    converted_matrix = matrix_multiply(
        bone["axis_matrix"],
        matrix_multiply(motion_matrix, bone["axis_inverse"]),
    )
    return converted_matrix, length_scale


def compute_joint_positions(skeleton, frame_channels):
    positions = {"root": skeleton["root"]["position"][:]}
    segment_rotations = {"root": identity_matrix()}

    root_values = frame_channels.get("root", [])
    root_position, root_rotation = root_rotation_matrix(root_values, skeleton)
    positions["root"] = root_position
    segment_rotations["root"] = root_rotation

    def walk(parent_name):
        parent_position = positions[parent_name]
        parent_rotation = segment_rotations[parent_name]

        for child_name in skeleton["children"].get(parent_name, []):
            bone = skeleton["bones"].get(child_name)
            if bone is None:
                continue

            child_values = frame_channels.get(child_name, [])
            child_motion_rotation, length_scale = bone_rotation_matrix(bone, child_values)
            child_segment_rotation = matrix_multiply(parent_rotation, child_motion_rotation)
            child_offset = apply_matrix(
                child_segment_rotation,
                vector_scale(bone["direction"], bone["length"] * length_scale),
            )
            child_position = vector_add(parent_position, child_offset)

            positions[child_name] = child_position
            segment_rotations[child_name] = child_segment_rotation
            walk(child_name)

    walk("root")
    return positions


def write_xyz_csv(asf_path: Path, amc_path: Path, output_path: Path):
    skeleton = parse_asf(asf_path)
    frames = parse_amc(amc_path)

    ordered_points = ["root"] + [bone_name for bone_name in skeleton["bone_order"] if bone_name in skeleton["bones"]]
    header = ["frame"]
    for point_name in ordered_points:
        header.extend([f"{point_name}_x", f"{point_name}_y", f"{point_name}_z"])

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)

        for frame_number, frame_channels in frames:
            positions = compute_joint_positions(skeleton, frame_channels)
            row = [frame_number]
            for point_name in ordered_points:
                point = positions.get(point_name)
                if point is None:
                    row.extend(["", "", ""])
                else:
                    row.extend(point)
            writer.writerow(row)

    return len(frames), len(ordered_points)


def prompt_for_paths():
    asf_text = input("Drag the ASF skeleton file here, then press Enter: ").strip()
    if not asf_text:
        raise ValueError("No ASF file was provided.")

    amc_text = input("Drag the AMC or TXT motion file here, then press Enter: ").strip()
    if not amc_text:
        raise ValueError("No AMC file was provided.")

    output_text = input(
        "Optional: drag a destination CSV here, or press Enter to save next to the AMC file: "
    ).strip()

    asf_path = Path(clean_path_text(asf_text)).expanduser().resolve()
    amc_path = Path(clean_path_text(amc_text)).expanduser().resolve()
    output_path = (
        Path(clean_path_text(output_text)).expanduser().resolve()
        if output_text
        else default_output_path(amc_path)
    )
    return asf_path, amc_path, output_path


def build_parser():
    parser = argparse.ArgumentParser(
        description="Convert an ASF skeleton plus AMC motion into a flat XYZ CSV for TouchDesigner."
    )
    parser.add_argument("asf", nargs="?", type=Path, help="Path to the ASF skeleton file")
    parser.add_argument("amc", nargs="?", type=Path, help="Path to the AMC or TXT motion file")
    parser.add_argument("output", nargs="?", type=Path, help="Optional output CSV path")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.asf is None or args.amc is None:
        asf_path, amc_path, output_path = prompt_for_paths()
        output_was_explicit = False
    else:
        asf_path = args.asf.expanduser().resolve()
        amc_path = args.amc.expanduser().resolve()
        output_path = (
            args.output.expanduser().resolve()
            if args.output is not None
            else default_output_path(amc_path)
        )
        output_was_explicit = args.output is not None

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        frame_count, point_count = write_xyz_csv(asf_path, amc_path, output_path)
    except PermissionError:
        if output_was_explicit:
            raise
        fallback_output = Path.cwd() / default_output_path(amc_path).name
        frame_count, point_count = write_xyz_csv(asf_path, amc_path, fallback_output)
        output_path = fallback_output
        print("Could not save next to the AMC file, so the CSV was saved here instead:")
        print(output_path)

    print(f"Wrote {frame_count} frames and XYZ coordinates for {point_count} points to {output_path}")


if __name__ == "__main__":
    main()
