#!/usr/bin/env python3

import argparse
import csv
import json
import io
import socket
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from asf_amc_to_xyz_csv import write_xyz_csv
from csv_to_osc_stream import (
    encode_osc_bundle,
    encode_osc_message,
    encode_point_axis_messages,
    load_point_csv,
)


ROOT_DIR = Path(__file__).resolve().parent
STATIC_FILES = {
    "/": ("mocap_interface.html", "text/html; charset=utf-8"),
    "/mocap_interface.css": ("mocap_interface.css", "text/css; charset=utf-8"),
    "/mocap_interface.js": ("mocap_interface.js", "application/javascript; charset=utf-8"),
    "/AtkinsonHyperlegibleNext-Regular.ttf": ("AtkinsonHyperlegibleNext-Regular.ttf", "font/ttf"),
    "/AtkinsonHyperlegibleNext-Bold.ttf": ("AtkinsonHyperlegibleNext-Bold.ttf", "font/ttf"),
}


@dataclass
class ConvertedDataset:
    csv_path: Path
    csv_bytes: bytes
    csv_name: str
    held_csv_bytes: bytes
    held_csv_name: str
    held2_csv_bytes: bytes
    held2_csv_name: str
    point_names: list[str]
    frame_count: int
    frames: list[dict]


@dataclass
class StreamStatus:
    active: bool = False
    host: str = "127.0.0.1"
    port: int = 7000
    fps: float = 30.0
    prefix: str = "/mocap"
    loop: bool = True
    selected_points: list[str] = field(default_factory=list)
    frames_sent: int = 0
    last_error: str | None = None


class StreamController:
    def __init__(self):
        self.thread = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.status = StreamStatus()

    def start(self, dataset: ConvertedDataset, host: str, port: int, fps: float, prefix: str, loop: bool, selected_points: list[str]):
        self.stop()
        self.stop_event = threading.Event()
        with self.lock:
            self.status = StreamStatus(
                active=True,
                host=host,
                port=port,
                fps=fps,
                prefix=prefix,
                loop=loop,
                selected_points=selected_points[:],
                frames_sent=0,
                last_error=None,
            )

        self.thread = threading.Thread(
            target=self._run_stream,
            args=(dataset, host, port, fps, prefix, loop, selected_points[:], self.stop_event),
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.stop_event.set()
            self.thread.join(timeout=1.0)
        with self.lock:
            self.status.active = False
        self.thread = None

    def _run_stream(self, dataset: ConvertedDataset, host: str, port: int, fps: float, prefix: str, loop: bool, selected_points: list[str], stop_event: threading.Event):
        point_filter = set(selected_points)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        target = (host, port)
        frame_duration = 1.0 / fps if fps > 0 else 0.0

        try:
            metadata_messages = [
                encode_osc_message(f"{prefix}/meta/point_count", [len(selected_points)]),
                encode_osc_message(f"{prefix}/meta/frame_count", [dataset.frame_count]),
            ]
            sock.sendto(encode_osc_bundle(metadata_messages), target)

            while not stop_event.is_set():
                for frame_index, frame in enumerate(dataset.frames):
                    if stop_event.is_set():
                        break

                    start_time = time.perf_counter()
                    messages = [
                        encode_osc_message(f"{prefix}/frame_index", [frame_index]),
                        encode_osc_message(
                            f"{prefix}/frame",
                            [int(frame["frame"])] if str(frame["frame"]).isdigit() else [str(frame["frame"])],
                        ),
                    ]

                    for point in frame["points"]:
                        if point["name"] in point_filter:
                            messages.extend(
                                encode_point_axis_messages(
                                    prefix,
                                    point["name"],
                                    point["xyz"],
                                )
                            )

                    sock.sendto(encode_osc_bundle(messages), target)

                    with self.lock:
                        self.status.frames_sent += 1

                    if frame_duration > 0:
                        remaining = frame_duration - (time.perf_counter() - start_time)
                        if remaining > 0:
                            time.sleep(remaining)

                if not loop:
                    break

        except Exception as error:  # noqa: BLE001
            with self.lock:
                self.status.last_error = str(error)
        finally:
            sock.close()
            with self.lock:
                self.status.active = False

    def snapshot(self):
        with self.lock:
            return {
                "active": self.status.active,
                "host": self.status.host,
                "port": self.status.port,
                "fps": self.status.fps,
                "prefix": self.status.prefix,
                "loop": self.status.loop,
                "selectedPoints": self.status.selected_points[:],
                "framesSent": self.status.frames_sent,
                "lastError": self.status.last_error,
            }


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.dataset: ConvertedDataset | None = None
        self.streamer = StreamController()

    def set_dataset(self, dataset: ConvertedDataset):
        with self.lock:
            self.dataset = dataset

    def get_dataset(self):
        with self.lock:
            return self.dataset


APP_STATE = AppState()


def json_response(handler: BaseHTTPRequestHandler, payload, status=HTTPStatus.OK):
    encoded = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def parse_multipart(handler: BaseHTTPRequestHandler):
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ValueError("Expected multipart/form-data request.")

    boundary_token = None
    for part in content_type.split(";"):
        piece = part.strip()
        if piece.startswith("boundary="):
            boundary_token = piece.split("=", 1)[1]
            break

    if boundary_token is None:
        raise ValueError("Multipart boundary was missing.")

    boundary = ("--" + boundary_token).encode("utf-8")
    content_length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(content_length)

    fields = {}
    for chunk in body.split(boundary):
        chunk = chunk.strip()
        if not chunk or chunk == b"--":
            continue

        headers_blob, _, content = chunk.partition(b"\r\n\r\n")
        if not _:
            continue

        headers_text = headers_blob.decode("utf-8", errors="replace")
        disposition_line = next(
            (line for line in headers_text.split("\r\n") if line.lower().startswith("content-disposition:")),
            None,
        )
        if disposition_line is None:
            continue

        name = None
        filename = None
        for piece in disposition_line.split(";"):
            trimmed = piece.strip()
            if trimmed.startswith("name="):
                name = trimmed.split("=", 1)[1].strip('"')
            elif trimmed.startswith("filename="):
                filename = trimmed.split("=", 1)[1].strip('"')

        if name is None:
            continue

        payload = content.rstrip(b"\r\n")
        fields[name] = {"filename": filename, "content": payload}

    return fields


def dataset_payload(dataset: ConvertedDataset | None):
    if dataset is None:
        return None

    return {
        "csvName": dataset.csv_name,
        "heldCsvName": dataset.held_csv_name,
        "held2CsvName": dataset.held2_csv_name,
        "frameCount": dataset.frame_count,
        "pointNames": dataset.point_names,
        "downloadUrl": "/api/download",
        "heldDownloadUrl": "/api/download?variant=held",
        "held2DownloadUrl": "/api/download?variant=held2",
    }


def sampled_csv_bytes_from_xyz_csv(csv_bytes: bytes, sample_every: int = 4):
    text = csv_bytes.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    if len(rows) < 2 or sample_every <= 1:
        return csv_bytes

    header = rows[0]
    data_rows = rows[1:]
    sampled_rows = [header]
    for row_index, row in enumerate(data_rows):
        if row_index % sample_every == 0:
            sampled_rows.append(row)

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(sampled_rows)
    return output.getvalue().encode("utf-8")


class MocapRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/status":
            dataset = APP_STATE.get_dataset()
            json_response(
                self,
                {
                    "dataset": dataset_payload(dataset),
                    "stream": APP_STATE.streamer.snapshot(),
                },
            )
            return

        if parsed.path == "/api/download":
            dataset = APP_STATE.get_dataset()
            if dataset is None:
                self.send_error(HTTPStatus.NOT_FOUND, "No converted CSV is available yet.")
                return

            variant = parse_qs(parsed.query).get("variant", ["base"])[0]
            if variant == "held":
                file_bytes = dataset.held_csv_bytes
                file_name = dataset.held_csv_name
            elif variant == "held2":
                file_bytes = dataset.held2_csv_bytes
                file_name = dataset.held2_csv_name
            else:
                file_bytes = dataset.csv_bytes
                file_name = dataset.csv_name

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{file_name}"')
            self.send_header("Content-Length", str(len(file_bytes)))
            self.end_headers()
            self.wfile.write(file_bytes)
            return

        if parsed.path in STATIC_FILES:
            filename, content_type = STATIC_FILES[parsed.path]
            file_path = ROOT_DIR / filename
            file_bytes = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(file_bytes)))
            self.end_headers()
            self.wfile.write(file_bytes)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/convert":
            try:
                fields = parse_multipart(self)
                asf = fields.get("asf")
                amc = fields.get("amc")
                if asf is None or amc is None:
                    raise ValueError("Both ASF and AMC files are required.")

                with tempfile.TemporaryDirectory(prefix="mocap_interface_") as temp_dir:
                    temp_path = Path(temp_dir)
                    asf_path = temp_path / (asf["filename"] or "input.asf")
                    amc_path = temp_path / (amc["filename"] or "input.amc")
                    csv_path = temp_path / ((Path(amc_path.name).stem or "output") + "_xyz.csv")

                    asf_path.write_bytes(asf["content"])
                    amc_path.write_bytes(amc["content"])
                    frame_count, _ = write_xyz_csv(asf_path, amc_path, csv_path)
                    csv_bytes = csv_path.read_bytes()
                    held2_csv_bytes = sampled_csv_bytes_from_xyz_csv(csv_bytes, sample_every=2)
                    held_csv_bytes = sampled_csv_bytes_from_xyz_csv(csv_bytes, sample_every=4)
                    frames, point_names = load_point_csv(csv_path)

                dataset = ConvertedDataset(
                    csv_path=ROOT_DIR / (Path(csv_path.name).name),
                    csv_bytes=csv_bytes,
                    csv_name=csv_path.name,
                    held_csv_bytes=held_csv_bytes,
                    held_csv_name=csv_path.stem + "_sample4.csv",
                    held2_csv_bytes=held2_csv_bytes,
                    held2_csv_name=csv_path.stem + "_sample2.csv",
                    point_names=point_names,
                    frame_count=frame_count,
                    frames=frames,
                )
                APP_STATE.set_dataset(dataset)
                json_response(
                    self,
                    {
                        "ok": True,
                        "dataset": dataset_payload(dataset),
                    },
                )
            except Exception as error:  # noqa: BLE001
                json_response(self, {"ok": False, "error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/stream/start":
            dataset = APP_STATE.get_dataset()
            if dataset is None:
                json_response(self, {"ok": False, "error": "Convert a dataset first."}, status=HTTPStatus.BAD_REQUEST)
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8"))
                host = str(payload.get("host", "127.0.0.1"))
                port = int(payload.get("port", 7000))
                fps = float(payload.get("fps", 30.0))
                prefix = str(payload.get("prefix", "/mocap")).rstrip("/") or "/mocap"
                loop = bool(payload.get("loop", True))
                selected_points = [
                    point_name
                    for point_name in payload.get("selectedPoints", [])
                    if point_name in dataset.point_names
                ]
                if not selected_points:
                    raise ValueError("Select at least one point to stream.")

                APP_STATE.streamer.start(dataset, host, port, fps, prefix, loop, selected_points)
                json_response(self, {"ok": True, "stream": APP_STATE.streamer.snapshot()})
            except Exception as error:  # noqa: BLE001
                json_response(self, {"ok": False, "error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/stream/stop":
            APP_STATE.streamer.stop()
            json_response(self, {"ok": True, "stream": APP_STATE.streamer.snapshot()})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format, *args):  # noqa: A003
        return


def main():
    parser = argparse.ArgumentParser(description="Run the local MoCap conversion and OSC streaming interface.")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host to bind")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port to bind")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), MocapRequestHandler)
    print(f"MoCap interface running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        APP_STATE.streamer.stop()
        server.server_close()


if __name__ == "__main__":
    main()
