"""Screen capture streaming script.

Captures the host machine's primary monitor and streams JPEG frames over a WebSocket
connection to the FastAPI server's /ws/producer endpoint.

Adjust SERVER_WS_URL to point to your deployed server (e.g., wss://your-domain/ws/producer).
"""
import time
import io
import mss
from PIL import Image
import websocket  # websocket-client
import threading
import traceback

# CONFIGURABLE: Set this to your deployed FastAPI WebSocket producer endpoint
SERVER_WS_URL = "ws://127.0.0.1:8000/ws/producer"  # change to wss://YOUR_DOMAIN/ws/producer when deployed
FRAME_RATE = 5  # target frames per second
JPEG_QUALITY = 60  # trade-off between size and clarity
MAX_DIMENSION = 1920  # optionally scale down large screens for bandwidth

_running = True


def capture_frames(send_func):
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor
        while _running:
            img = sct.grab(monitor)
            im = Image.frombytes("RGB", (img.width, img.height), img.rgb)
            # Optional downscale if larger than MAX_DIMENSION
            w, h = im.size
            scale = min(1.0, MAX_DIMENSION / max(w, h))
            if scale < 1.0:
                im = im.resize((int(w * scale), int(h * scale)))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            data = buf.getvalue()
            try:
                send_func(data)
            except Exception as e:
                break
            time.sleep(max(0, 1 / FRAME_RATE))


def on_open(ws):
    print("Connected to server. Starting capture...")
    def send_binary_frame(data):
        try:
            # Use send() with opcode parameter for binary data
            ws.send(data, opcode=websocket.ABNF.OPCODE_BINARY)
        except Exception as e:
            raise e
    
    thread = threading.Thread(target=capture_frames, args=(send_binary_frame,), daemon=True)
    thread.start()


def on_close(ws, close_status_code, close_msg):
    global _running
    _running = False
    print(f"Connection closed. code={close_status_code} msg={close_msg}")


def on_error(ws, error):
    print("WebSocket error:", error)
    traceback.print_exc()


def main():
    print(f"Connecting to {SERVER_WS_URL} ...")
    ws = websocket.WebSocketApp(
        SERVER_WS_URL,
        on_open=on_open,
        on_close=on_close,
        on_error=on_error,
    )
    ws.run_forever()


if __name__ == "__main__":
    main()
