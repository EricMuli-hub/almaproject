import os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import uvicorn
from app.api import create_app
uvicorn.run(create_app(), host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
