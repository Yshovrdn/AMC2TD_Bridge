# AMC2TD Bridge

Convert `ASF` + `AMC` mocap files into XYZ CSV data for TouchDesigner, then stream selected joints over OSC.

## What It Does

- converts `ASF` + `AMC` into joint-position CSVs
- exports `120 Hz`, `60 Hz`, and `30 Hz` CSV variants
- streams selected joints over OSC with `_x`, `_y`, `_z` suffixes
- includes a small local web interface for upload, download, and streaming

Example OSC addresses:

- `/mocap/root_x`
- `/mocap/root_y`
- `/mocap/root_z`
- `/mocap/lhand_x`

## Main App

Run:

```bash
./run_mocap_interface.command
```

Then open:

```text
http://127.0.0.1:8765
```

## Basic Workflow

1. Upload a matching `ASF` file and `AMC` file.
2. Download one of the generated XYZ CSVs.
3. Select the joints you want.
4. Stream them to TouchDesigner over OSC.

Note:
`AMC` alone is not enough for full-body XYZ reconstruction. The `ASF` file provides the skeleton definition.

## CSV Outputs

- `120 Hz CSV`
  Original reconstructed frame rate.
- `60 Hz Sampled CSV`
  Keeps every 2nd frame.
- `30 Hz Sampled CSV`
  Keeps every 4th frame.

## TouchDesigner

Default OSC target:

- host: `127.0.0.1`
- port: `7000`

In TouchDesigner:

1. Add an `OSC In CHOP` or `OSC In DAT`.
2. Set the port to `7000` or whatever you choose in the app.
3. Start the stream from the browser UI.

## Other Tools

- `asf_amc_to_xyz_csv.py`
  Convert `ASF` + `AMC` to XYZ CSV from the command line.
- `csv_to_osc_stream.py`
  Stream an XYZ CSV over OSC without the web interface.
- `point_visualizer.html`
  Minimal 3D CSV viewer.
- `amc_to_csv.py`
  Flatten AMC-style text into a spreadsheet-style CSV.

## Command Line

Convert to XYZ CSV:

```bash
python3 asf_amc_to_xyz_csv.py /path/to/skeleton.asf /path/to/motion.amc
```

Stream CSV over OSC:

```bash
python3 csv_to_osc_stream.py /path/to/file_xyz.csv --host 127.0.0.1 --port 7000 --fps 30
```

## Requirements

- Python 3
- local browser
- no external Python dependencies

## CMU Mocap Credit

This project is built for CMU-style mocap data and should credit the original source when used with that dataset.

- CMU Graphics Lab Motion Capture Database:
  [https://mocap.cs.cmu.edu/](https://mocap.cs.cmu.edu/)
- CMU info page:
  [https://mocap.cs.cmu.edu/info.php](https://mocap.cs.cmu.edu/info.php)
- CMU FAQ:
  [https://mocap.cs.cmu.edu/faqs.php](https://mocap.cs.cmu.edu/faqs.php)
- CMU `ASF` + `AMC` zip download:
  [https://mocap.cs.cmu.edu/allasfamc.zip](https://mocap.cs.cmu.edu/allasfamc.zip)

If you publish work using CMU mocap data, check the official CMU site for their current attribution guidance.
