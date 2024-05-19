import asyncio

from fastapi import FastAPI
from pydantic import BaseModel

from consumer.coordinator import TransactionCoordinator

app: FastAPI = FastAPI()


class RequestPayload(BaseModel):
    groupId: str
    action: str


@app.post("/dtc/")
async def process_request(payload: RequestPayload) -> dict:
    transaction_state = await asyncio.run(TransactionCoordinator().coordinate(payload.groupId, payload.action))
    return {"State": transaction_state.value}
