# Minimal Screen Share (FastAPI + WebSocket)

A lightweight screen broadcasting setup: a Python capture script streams JPEG frames to a FastAPI server over WebSockets; connected browser clients view the live screen full-screen.

> NOTE: Traditional Vercel Python Serverless Functions historically have limited / brittle support for long‑lived WebSocket connections. If you encounter disconnects or lack of support, consider an alternative host (Fly.io, Render, Railway) or a Node/Edge function on Vercel. This repo still provides the desired FastAPI structure.

## Structure
```
server/main.py            # FastAPI app with producer + viewer WebSockets and HTML page
api/index.py              # Vercel entrypoint re-exporting the FastAPI app
script/capture_and_stream.py  # Host machine screen capture & streaming producer
vercel.json               # Vercel configuration (routes + function settings)
requirements.txt          # Python dependencies
```

## How it works
1. Run the capture script on the host machine. It opens a WebSocket to `/ws/producer` and sends JPEG frames at a target FPS.
2. Browser clients connect to `/ws/viewer` and receive binary JPEG frames, updating an `<img>` tag for full-screen display.
3. Connect / Disconnect buttons manage viewer WebSocket lifecycle.

## Running Locally
Python 3.11 is the Vercel runtime; however this project can run on Python 3.13 locally with a few build prerequisites (Pillow may compile from source).

Install dependencies:
```bash
python -m venv .venv  # 3.11 or 3.13 works; deployment uses 3.11
source .venv/bin/activate
pip install -r requirements.txt
```
Start server (development):
```bash
uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
```
Run capture script (in a second terminal):
```bash
python script/capture_and_stream.py
```
Open: http://localhost:8000 — the viewer now auto‑connects (no buttons) and the status bar will show:
* connecting… then connected when the WebSocket viewer link is established.
* disconnected - start/verify host script if the producer is not sending frames.
It will retry automatically with backoff; start the host capture script to see frames.

### If Pillow fails to build on Python 3.13
Install build tooling & jpeg libraries, then reinstall:
```bash
xcode-select --install            # ensure Command Line Tools
brew install jpeg libtiff webp little-cms2 libjpeg-turbo
pip install -U pip setuptools wheel
pip install --no-cache-dir -r requirements.txt
```
If still failing, try: `pip install --no-binary=:all: Pillow` or switch to Python 3.11.

### Why loosened versions?
`requirements.txt` uses compatible ranges (>= / <) so Python 3.13 can pick newer wheels.

## Configuration
Edit `script/capture_and_stream.py`:
- `SERVER_WS_URL`: set to your deployed `wss://your-domain/ws/producer` for production.
- `FRAME_RATE`: adjust (5–10 is reasonable for bandwidth). Higher FPS increases CPU & bandwidth.
- `JPEG_QUALITY`: 40–70 trade-off between clarity and size.
- `MAX_DIMENSION`: downscale large screens.

## Vercel Deployment
```bash
# Login & deploy
vercel login
vercel deploy --prod
```
Current `vercel.json` uses the legacy `builds` array with the `@vercel/python` builder:
```json
{
	"version": 2,
	"builds": [{ "src": "api/index.py", "use": "@vercel/python" }],
	"routes": [
		{ "src": "/ws/(producer|viewer)", "dest": "/api/index.py" },
		{ "src": "/(.*)", "dest": "/api/index.py" }
	]
}
```
This resolves the build error: `Function Runtimes must have a valid version` which was triggered by an invalid `functions` runtime specification. 

⚠ WebSocket Limitation: Vercel's Python serverless functions do not maintain truly persistent WebSocket connections (they are designed for short-lived request handling). Even if deployment succeeds, long-running streaming sessions may disconnect or never upgrade properly. For production real-time streaming, prefer one of:
1. Host FastAPI (with native WebSockets) on Render, Fly.io, Railway, or a small VPS.
2. Serve only a static/Next.js viewer page on Vercel that connects to the external domain (e.g., `wss://your-fastapi-host/ws/viewer`).
3. Use a managed real-time layer (Ably, Pusher, Socket.IO service) and let the capture script publish frames there; browser subscribes directly.

Suggested Split Architecture:
```
Producer (desktop) --wss--> FastAPI server (Render/Fly) --fan-out--> Viewers
															 ^
															 |
											Static viewer page (Vercel)
```
Update `script/capture_and_stream.py` to point `SERVER_URL` explicitly to the external FastAPI host; keep Vercel for the viewer UX only.

If WebSockets aren't stable on Vercel:
- Switch to an external WebSocket gateway (e.g., Ably, Pusher) and have the FastAPI function only perform signaling / auth.
- Or migrate the FastAPI app to a platform with persistent ASGI support.

## Edge Cases & Considerations
- Producer reconnect: If the producer disconnects, viewers keep their connection but receive no new frames.
- Multiple producers: Currently restricted to one; second connection to `/ws/producer` is rejected (code 4000).
- Bandwidth: JPEG compression reduces payload; further reduce by lowering resolution or FPS.
- Backpressure: Not currently throttled. If viewer count grows large, consider queue + dropping late frames.
- Security: No auth layer. Add a token check on both WebSocket endpoints for production.

## Adding Auth (Optional Sketch)
```python
# Example: expect ?token=SECRET on websocket URL
# Validate before adding to viewers / assigning producer.
```

## Future Improvements
- Use WebRTC (aiortc) for built-in congestion control & lower latency.
- Delta frame (diff) encoding or WebP for better compression.
- Heartbeat / ping frames to detect dead connections sooner.

## License
MIT
