#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path


JOINT_AXIS_LABELS = {
    "root": ["tx", "ty", "tz", "rx", "ry", "rz"],
    "lowerback": ["rx", "ry", "rz"],
    "upperback": ["rx", "ry", "rz"],
    "thorax": ["rx", "ry", "rz"],
    "lowerneck": ["rx", "ry", "rz"],
    "upperneck": ["rx", "ry", "rz"],
    "head": ["rx", "ry", "rz"],
    "rclavicle": ["ry", "rz"],
    "lclavicle": ["ry", "rz"],
    "rhumerus": ["rx", "ry", "rz"],
    "lhumerus": ["rx", "ry", "rz"],
    "rradius": ["rx"],
    "lradius": ["rx"],
    "rwrist": ["rx"],
    "lwrist": ["rx"],
    "rhand": ["rx", "rz"],
    "lhand": ["rx", "rz"],
    "rfingers": ["rx"],
    "lfingers": ["rx"],
    "rthumb": ["rx", "rz"],
    "lthumb": ["rx", "rz"],
    "rfemur": ["rx", "ry", "rz"],
    "lfemur": ["rx", "ry", "rz"],
    "rtibia": ["rx"],
    "ltibia": ["rx"],
    "rfoot": ["rx", "rz"],
    "lfoot": ["rx", "rz"],
    "rtoes": ["rx"],
    "ltoes": ["rx"],
}


def clean_path_text(text: str) -> str:
    return text.strip().strip('"').strip("'")


def default_output_path(input_path: Path) -> Path:
    name = input_path.name

    if name.lower().endswith(".amc.txt"):
        return input_path.with_name(name[:-8] + ".csv")

    if input_path.suffix.lower() in {".txt", ".amc"}:
        return input_path.with_suffix(".csv")

    return input_path.with_name(input_path.name + ".csv")


def parse_amc(path: Path):
    frames = []
    joint_order = []
    max_widths = {}
    current_frame_number = None
    current_frame_values = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()

            if not line or line.startswith("#!") or line.startswith(":"):
                continue

            if line.isdigit():
                if current_frame_values is not None:
                    frames.append((current_frame_number, current_frame_values))
                current_frame_number = int(line)
                current_frame_values = {}
                continue

            if current_frame_values is None:
                continue

            parts = line.split()
            if len(parts) < 2:
                raise ValueError(f"Malformed data line at {path}:{line_number}: {raw_line.rstrip()}")

            joint_name = parts[0]
            joint_values = parts[1:]

            if joint_name not in max_widths:
                joint_order.append(joint_name)
                max_widths[joint_name] = 0

            max_widths[joint_name] = max(max_widths[joint_name], len(joint_values))
            current_frame_values[joint_name] = joint_values

    if current_frame_values is not None:
        frames.append((current_frame_number, current_frame_values))

    if not frames:
        raise ValueError(f"No frame data found in {path}")

    return frames, joint_order, max_widths


def axis_labels_for_joint(joint_name: str, width: int):
    labels = JOINT_AXIS_LABELS.get(joint_name)
    if labels and len(labels) == width:
        return labels

    if joint_name == "root" and width == 6:
        return ["tx", "ty", "tz", "rx", "ry", "rz"]

    if width == 3:
        return ["rx", "ry", "rz"]

    return [f"value_{index}" for index in range(1, width + 1)]


def write_csv(input_path: Path, output_path: Path):
    frames, joint_order, max_widths = parse_amc(input_path)

    header = ["frame"]
    for joint_name in joint_order:
        axis_labels = axis_labels_for_joint(joint_name, max_widths[joint_name])
        header.extend(f"{joint_name}_{axis}" for axis in axis_labels)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)

        for frame_number, frame_values in frames:
            row = [frame_number]
            for joint_name in joint_order:
                values = frame_values.get(joint_name, [])
                padded_values = values + [""] * (max_widths[joint_name] - len(values))
                row.extend(padded_values)
            writer.writerow(row)

    return len(frames), len(header) - 1


def build_parser():
    parser = argparse.ArgumentParser(
        description="Convert AMC-style motion text files into a flat CSV spreadsheet."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="Path to the AMC or TXT file to convert",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="Optional output CSV path (defaults to the input name with a .csv extension)",
    )
    return parser


def prompt_for_paths():
    input_text = input("Drag your AMC/TXT file here, then press Enter: ").strip()
    if not input_text:
        raise ValueError("No input file was provided.")

    input_path = Path(clean_path_text(input_text)).expanduser().resolve()

    output_text = input(
        "Optional: drag a destination CSV here, or press Enter to save next to the input file: "
    ).strip()

    output_path = (
        Path(clean_path_text(output_text)).expanduser().resolve()
        if output_text
        else default_output_path(input_path)
    )

    return input_path, output_path


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.input is None:
        input_path, output_path = prompt_for_paths()
        output_was_explicit = False
    else:
        input_path = args.input.expanduser().resolve()
        output_path = (
            args.output.expanduser().resolve()
            if args.output is not None
            else default_output_path(input_path)
        )
        output_was_explicit = args.output is not None

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        frame_count, value_column_count = write_csv(input_path, output_path)
    except PermissionError:
        if output_was_explicit:
            raise

        fallback_output = Path.cwd() / default_output_path(input_path).name
        frame_count, value_column_count = write_csv(input_path, fallback_output)
        output_path = fallback_output
        print(
            "Could not save next to the input file, so the CSV was saved here instead:"
        )
        print(output_path)

    print(
        f"Wrote {frame_count} frames and {value_column_count} value columns to {output_path}"
    )


if __name__ == "__main__":
    main()
