import uvicorn
from app.config import settings

if __name__ == "__main__":
    print(f"Starting CWA Rain Fetcher server on http://{settings.host}:{settings.port} ...")
    uvicorn.run(
        "app.api:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
