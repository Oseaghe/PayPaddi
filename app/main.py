from fastapi import FastAPI
from app.database import Base, engine
from app.routers import merchants, payments, webhooks

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Kora Hackathon API", version="1.0.0")

app.include_router(merchants.router)
app.include_router(payments.router)
app.include_router(webhooks.router)


@app.get("/health")
def health():
    return {"status": "ok"}
