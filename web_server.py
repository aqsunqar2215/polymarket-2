import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import json
import os

app = FastAPI()

# Создаем папку static, если её нет
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get_index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/data")
async def get_data():
    try:
        # Читаем данные, которые сохраняет main.py
        with open("bot_status.json", "r") as f:
            return json.load(f)
    except:
        return {"status": "error", "message": "Бот не запущен"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)