import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

DATA_DIR = "data"
JSON_FILE = os.path.join(DATA_DIR, "dashboard_data.json")

@app.get("/api/data")
def get_data():
    """Reads the pre-computed dashboard data from the JSON file."""
    if not os.path.exists(JSON_FILE):
        # Return an error or empty state if the update script hasn't been run yet
        raise HTTPException(status_code=503, detail="Dashboard data not generated yet. Please run update_data.py")
        
    try:
        with open(JSON_FILE, "r") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading data: {str(e)}")

@app.get("/")
def serve_home():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())
