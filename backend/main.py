from fastapi import FastAPI

from backend.api.chat import router as chat_router
from backend.api.upload import router as upload_router


app = FastAPI(title="Department AI MVP", version="0.1.0")

app.include_router(chat_router)
app.include_router(upload_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
