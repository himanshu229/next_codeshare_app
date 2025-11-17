from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import Set
import asyncio
import logging

logger = logging.getLogger("screen_share")
if not logger.handlers:
  handler = logging.StreamHandler()
  formatter = logging.Formatter("[%(levelname)s] %(message)s")
  handler.setFormatter(formatter)
  logger.addHandler(handler)
logger.setLevel(logging.INFO)

app = FastAPI()
viewers: Set[WebSocket] = set()
producer: WebSocket | None = None

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Live Screen</title>
  <style>
    html,body { margin:0; padding:0; background:#000; height:100%; overflow:hidden; font-family:system-ui,sans-serif; }
    #statusBar { position:fixed; top:8px; left:8px; padding:4px 8px; background:rgba(0,0,0,0.6); border:1px solid #222; border-radius:4px; font-size:13px; color:#0f0; z-index:20; }
    #statusBar.error { color:#f33; }
    #screen { width:100%; height:100%; object-fit:contain; background:#000; display:block; }
    #overlay { position:fixed; inset:0; display:flex; align-items:center; justify-content:center; background:#000; color:#f33; font-size:clamp(16px,4vw,42px); font-weight:600; text-align:center; padding:2rem; z-index:10; }
    #overlay.hidden { display:none; }
  </style>
</head>
<body>
  <div id="statusBar">connecting...</div>
  <div id="overlay">REMOTE DISCONNECTED<br/>Start the host capture script.</div>
  <img id="screen" alt="Waiting for stream..." />
<script>
const statusEl = document.getElementById('statusBar');
const imgEl = document.getElementById('screen');
const overlayEl = document.getElementById('overlay');

function setStatus(text, error = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle('error', error);
}

function showOverlay(msg) {
  overlayEl.textContent = msg;
  overlayEl.classList.remove('hidden');
}

function hideOverlay() {
  overlayEl.classList.add('hidden');
}

console.log('Starting WebSocket connection...');
setStatus('connecting...');

// Dynamically build WebSocket URL so it works in local dev and production deployments.
const WS_BASE = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host;
const WS_URL = WS_BASE + '/ws/viewer';
console.log('Connecting to viewer WS:', WS_URL);
const ws = new WebSocket(WS_URL);
ws.binaryType = 'arraybuffer';

ws.onopen = function() {
  setStatus('connected');
};

ws.onclose = function(event) {
  setStatus('viewer disconnected', true);
  showOverlay('REMOTE DISCONNECTED\\nStart the host capture script.');
};

ws.onerror = function(error) {
  setStatus('error - check host script', true);
};

ws.onmessage = function(event) {
  if (typeof event.data === 'string') {
    if (event.data === 'producer:connected') {
      hideOverlay();
      setStatus('streaming');
    } else if (event.data === 'producer:disconnected') {
      showOverlay('REMOTE DISCONNECTED\\nAwaiting host capture script...');
      setStatus('waiting');
    }
  } else {
    hideOverlay();
    setStatus('streaming');
    
    const blob = new Blob([event.data], { type: 'image/jpeg' });
    const url = URL.createObjectURL(blob);
    imgEl.src = url;
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
};
</script>
</body>
</html>
"""

@app.get("/")
async def index():
  return HTMLResponse(HTML_PAGE)

async def _broadcast_control(message: str):
  if viewers:
    await asyncio.gather(*[v.send_text(message) for v in list(viewers)])

@app.websocket("/ws/producer")
async def ws_producer(ws: WebSocket):
  global producer
  logger.info("Producer attempting to connect...")
  await ws.accept()
  logger.info(f"Producer connection accepted. Current producer: {producer}")
  if producer is not None:
    logger.warning("Rejecting new producer: already connected")
    await ws.close(code=4000)
    logger.info("Producer connection closed: already connected.")
    return
  producer = ws
  logger.info("Producer connected and set as active.")
  await _broadcast_control("producer:connected")
  try:
    while True:
      data = await ws.receive_bytes()
      size = len(data)
      if size == 0:
        continue
      if viewers:
        await asyncio.gather(*[v.send_bytes(data) for v in list(viewers) if v], return_exceptions=True)
  except WebSocketDisconnect:
    logger.info("Producer disconnected (WebSocketDisconnect)")
  except Exception as e:
    logger.exception(f"Producer exception: {e}")
  finally:
    producer = None
    logger.info("Producer slot cleared (finally block)")
    await _broadcast_control("producer:disconnected")

@app.websocket("/ws/viewer")
async def ws_viewer(ws: WebSocket):
  await ws.accept()
  viewers.add(ws)
  # Send initial state
  try:
    if producer is None:
      await ws.send_text("producer:disconnected")
    else:
      await ws.send_text("producer:connected")
    while True:
      # Viewers do not send data; just keep connection alive.
      msg = await ws.receive_text()
      # Ignore any text messages; could implement ping/pong or commands.
  except WebSocketDisconnect:
    logger.info("Viewer disconnected")
  except Exception as e:
    logger.exception(f"Viewer exception: {e}")
  finally:
    viewers.discard(ws)
    logger.info(f"Viewer removed; {len(viewers)} remaining")

# Health check route
@app.get("/health")
async def health():
    return {"status": "ok", "producer_connected": producer is not None, "viewer_count": len(viewers)}
