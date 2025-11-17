# Vercel entrypoint mapping to FastAPI app
from server.main import app  # Vercel expects an 'app' variable for ASGI

# If running locally with `uvicorn api.index:app --reload`
# the imported FastAPI instance will serve.
