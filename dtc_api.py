import asyncio

from fastapi import FastAPI
from pydantic import BaseModel
from tenacity import RetryError

from consumer.coordinator import TransactionCoordinator

app: FastAPI = FastAPI()


class RequestPayload(BaseModel):
    groupId: str
    action: str


@app.post("/dtc/")
async def process_request(payload: RequestPayload) -> dict:
    try:
        transaction_state = await asyncio.run(TransactionCoordinator().coordinate(payload.groupId, payload.action))
    except RetryError:
        # TODO: Take action(s) for reporting: Logging, Sending Alerts; maybe, escalate_for_manual_intervention()
        pass
    return {"State": transaction_state.value}
