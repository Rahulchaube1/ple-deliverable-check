"""Synthetic protocol checks. Run with python -m unittest discover -s tests."""
import asyncio
import base64
import contextlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve as websocket_server

import inspect_output
import serve
import taskbridge


class Formats(unittest.TestCase):
    def test_valid_and_broken_office_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", "<document/>")
            self.assertGreater(inspect_output.inspect(str(path))["bytes"], 0)
            path.write_bytes(b"incomplete")
            with self.assertRaises(zipfile.BadZipFile):
                inspect_output.inspect(str(path))

    def test_rejects_truncated_pdf_and_ifc(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, data in [("drawing.pdf", b"%PDF-1.7"), ("model.ifc", b"ISO-10303-21;")]:
                path = Path(directory) / name
                path.write_bytes(data)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    inspect_output.inspect(str(path))


class Protocol(unittest.IsolatedAsyncioTestCase):
    async def test_missing_deliverable_is_repaired_before_done(self):
        calls = [
            ("declare", {"paths": ["result.json"], "destination": "task folder"}),
            ("finish", {"summary": "Completed"}),
            ("write", {"path": "result.json", "content": '{"flow_lps": 12}'}),
            ("finish", {"summary": "Confirmed result.json"}),
        ]
        requests = []

        class Model(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(request)
                index = len(requests) - 1
                name, args = calls[index]
                msg = {"role": "assistant", "content": None, "tool_calls": [{
                    "id": str(index), "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)}}]}
                payload = json.dumps({"choices": [{"message": msg}], "usage": {
                    "prompt_tokens": 10, "completion_tokens": 5}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            server = stack.enter_context(ThreadingHTTPServer(("127.0.0.1", 0), Model))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            stack.callback(server.shutdown)
            stack.enter_context(patch.dict(os.environ, {
                "MODEL_NAME": "fixture", "MODEL_API_KEY": "fixture",
                "MODEL_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                "HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "", "http_proxy": "", "https_proxy": "", "all_proxy": "",
                "PLE_CHECK_OUTPUTS": "1", "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}))
            async with websocket_server(lambda ws: taskbridge._session(ws, serve.solve), "127.0.0.1", 0) as ws_server:
                port = ws_server.sockets[0].getsockname()[1]
                async with connect(f"ws://127.0.0.1:{port}", proxy=None) as ws:
                    await ws.send(json.dumps({"type": "task", "instruction": "Write result.json",
                                              "workdir": tmp, "limits": {"agent_timeout_sec": 60}}))
                    usages = 0
                    while True:
                        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                        kind = frame["type"]
                        if kind == "done":
                            self.assertEqual(frame["final_message"], "Confirmed result.json")
                            break
                        if kind == "usage":
                            usages += 1
                            continue
                        if kind == "exec":
                            args = shlex.split(frame["command"])
                            self.assertEqual(args[:3], ["python3", "-c", serve.CHECKER])
                            run = subprocess.run([sys.executable, *args[1:]], cwd=tmp,
                                                 capture_output=True, text=True, check=False)
                            fields = {"exit_code": run.returncode, "output": run.stdout}
                        elif kind == "write_file":
                            self.assertEqual(frame["path"], "result.json")
                            path = Path(tmp) / frame["path"]
                            size = path.write_bytes(base64.b64decode(frame["content_b64"]))
                            fields = {"ok": True, "size": size}
                        else:
                            self.fail(f"unexpected frame {kind}")
                        await ws.send(json.dumps({"type": "result", "id": frame["id"], **fields}))
            self.assertEqual(usages, 4)
            self.assertIn("Delivery check failed", requests[2]["messages"][-1]["content"])
            self.assertEqual(json.loads((Path(tmp) / "result.json").read_text()), {"flow_lps": 12})
