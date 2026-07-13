from __future__ import annotations

import base64
import hashlib
import json
import socketserver
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent
COMMENTS_DIR = ROOT / "comments"
HOST = "localhost"
PORT = 8765
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def build_ws_accept(key: str) -> str:
    digest = hashlib.sha1((key + WS_GUID).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def recv_exact(stream, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = stream.read(length - len(data))
        if not chunk:
            raise ConnectionError("Socket closed while receiving data")
        data.extend(chunk)
    return bytes(data)


def read_ws_frame(stream) -> str:
    header = recv_exact(stream, 2)
    first_byte, second_byte = header[0], header[1]
    opcode = first_byte & 0x0F
    masked = bool(second_byte & 0x80)
    payload_length = second_byte & 0x7F

    if opcode == 0x8:
        raise ConnectionError("Client closed the WebSocket")

    if opcode != 0x1:
        raise ValueError(f"Unsupported opcode: {opcode}")

    if payload_length == 126:
        payload_length = struct.unpack("!H", recv_exact(stream, 2))[0]
    elif payload_length == 127:
        payload_length = struct.unpack("!Q", recv_exact(stream, 8))[0]

    if not masked:
        raise ValueError("Expected masked client frame")

    mask = recv_exact(stream, 4)
    payload = bytearray(recv_exact(stream, payload_length))
    for index in range(payload_length):
        payload[index] ^= mask[index % 4]

    return payload.decode("utf-8")


def send_ws_text(stream, message: str) -> None:
    payload = message.encode("utf-8")
    frame = bytearray()
    frame.append(0x81)

    length = len(payload)
    if length < 126:
        frame.append(length)
    elif length < 65536:
        frame.append(126)
        frame.extend(struct.pack("!H", length))
    else:
        frame.append(127)
        frame.extend(struct.pack("!Q", length))

    frame.extend(payload)
    stream.write(frame)
    stream.flush()


class CommentsWebSocketHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        request_line = self.rfile.readline().decode("utf-8", errors="ignore").strip()
        if not request_line:
            return

        headers: dict[str, str] = {}
        while True:
            line = self.rfile.readline().decode("utf-8", errors="ignore")
            if line in ("\r\n", "\n", ""):
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        if "upgrade" not in headers.get("connection", "").lower() or headers.get("upgrade", "").lower() != "websocket":
            self.wfile.write(
                b"HTTP/1.1 426 Upgrade Required\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                b"Connection: close\r\n\r\n"
                b"This server expects a WebSocket connection.\n"
            )
            self.wfile.flush()
            return

        key = headers.get("sec-websocket-key")
        if not key:
            self.wfile.write(
                b"HTTP/1.1 400 Bad Request\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                b"Connection: close\r\n\r\n"
                b"Missing Sec-WebSocket-Key header.\n"
            )
            self.wfile.flush()
            return

        accept_value = build_ws_accept(key)
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_value}\r\n\r\n"
        )
        self.wfile.write(response.encode("utf-8"))
        self.wfile.flush()

        try:
            message = read_ws_frame(self.rfile)
            payload = json.loads(message)
            post_id = str(payload.get("post_id") or "post").strip() or "post"
            csv_content = payload.get("csv")
            if not isinstance(csv_content, str) or not csv_content.strip():
                raise ValueError("Missing csv content")

            COMMENTS_DIR.mkdir(exist_ok=True)
            safe_post_id = "".join(
                ch for ch in post_id if ch.isalnum() or ch in ("-", "_")
            ) or "post"
            output_path = COMMENTS_DIR / f"instagram-comments-{safe_post_id}.csv"
            output_path.write_text(csv_content, encoding="utf-8", newline="")

            response_payload = json.dumps(
                {
                    "ok": True,
                    "filename": output_path.name,
                    "path": str(output_path),
                }
            )
            send_ws_text(self.wfile, response_payload)
        except Exception as exc:
            send_ws_text(self.wfile, json.dumps({"ok": False, "error": str(exc)}))


class ThreadedWebSocketServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    COMMENTS_DIR.mkdir(exist_ok=True)
    with ThreadedWebSocketServer((HOST, PORT), CommentsWebSocketHandler) as server:
        print(f"Saving Instagram comments to {COMMENTS_DIR}")
        print(f"Listening for WebSocket connections on ws://{HOST}:{PORT}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")


if __name__ == "__main__":
    main()
