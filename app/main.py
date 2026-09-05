from fastapi import FastAPI

from app.domains.auth.router import router as auth_router

app = FastAPI(title="ATS FastAPI")

app.include_router(auth_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
