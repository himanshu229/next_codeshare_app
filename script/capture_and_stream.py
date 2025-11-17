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
# For local development, use: "ws://127.0.0.1:8000/ws/producer"
# For production (Vercel), use: "wss://your-domain.vercel.app/ws/producer"
SERVER_URL = "https://next-codeshare-app.vercel.app"  # Change this to your Vercel URL or keep empty for local
LOCAL_SERVER = "127.0.0.1:8000"

# Auto-detect WebSocket URL based on server configuration
if SERVER_URL and SERVER_URL.startswith("https://"):
    # Production: Convert https:// to wss://
    SERVER_WS_URL = SERVER_URL.replace("https://", "wss://") + "/ws/producer"
    print(f"Using production server: {SERVER_WS_URL}")
elif SERVER_URL and SERVER_URL.startswith("http://"):
    # HTTP: Convert http:// to ws://
    SERVER_WS_URL = SERVER_URL.replace("http://", "ws://") + "/ws/producer"
    print(f"Using HTTP server: {SERVER_WS_URL}")
else:
    # Local development
    SERVER_WS_URL = f"ws://{LOCAL_SERVER}/ws/producer"
    print(f"Using local development server: {SERVER_WS_URL}")

FRAME_RATE = 5  # target frames per second
JPEG_QUALITY = 60  # trade-off between size and clarity
MAX_DIMENSION = 1920  # optionally scale down large screens for bandwidth
RECONNECT_TIMEOUT = 600  # 10 minutes in seconds

_running = True
_should_reconnect = True


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
    global _running
    _running = True
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
    if _should_reconnect:
        print("Connection lost. Will attempt to reconnect...")


def on_error(ws, error):
    if _should_reconnect:
        print("WebSocket error occurred. Will attempt to reconnect...")
    else:
        print("WebSocket error:", error)
        traceback.print_exc()


def connect_with_retry():
    """Attempt to connect with exponential backoff for up to 10 minutes"""
    global _should_reconnect
    start_time = time.time()
    attempt = 1
    
    while time.time() - start_time < RECONNECT_TIMEOUT and _should_reconnect:
        try:
            print(f"Connection attempt #{attempt} to {SERVER_WS_URL}")
            
            ws = websocket.WebSocketApp(
                SERVER_WS_URL,
                on_open=on_open,
                on_close=on_close,
                on_error=on_error,
            )
            ws.run_forever()
            
            # If we get here, the connection ended normally
            if not _should_reconnect:
                break
                
        except KeyboardInterrupt:
            print("\nStopping reconnection attempts...")
            _should_reconnect = False
            break
        except Exception as e:
            print(f"Failed to connect: {e}")
        
        if _should_reconnect and time.time() - start_time < RECONNECT_TIMEOUT:
            # Exponential backoff: 2, 4, 8, 16, 30, 30, 30... seconds (max 30s)
            delay = min(30, 2 ** min(attempt - 1, 4))
            print(f"Waiting {delay} seconds before retry...")
            time.sleep(delay)
            attempt += 1
    
    if time.time() - start_time >= RECONNECT_TIMEOUT:
        print("Reconnection timeout reached (10 minutes). Giving up.")
    else:
        print("Connection attempts stopped.")


def main():
    global _running, _should_reconnect
    
    try:
        connect_with_retry()
    except KeyboardInterrupt:
        print("\nShutting down...")
        _should_reconnect = False
        _running = False


if __name__ == "__main__":
    main()
