from backend.main import app

if __name__ == "__main__":
    import uvicorn
    # Synchronized with the high-fidelity UI overhaul and port transition
    uvicorn.run(app, host="127.0.0.1", port=8080)

