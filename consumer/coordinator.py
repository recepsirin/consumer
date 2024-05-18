from __future__ import annotations

import asyncio
import configparser
from collections.abc import Iterator
from typing import Any, Coroutine

import httpx
from tenacity import RetryError, Retrying, stop_after_attempt, wait_exponential

from consumer.client import APIClient

retry_strategy = Retrying(
    stop=stop_after_attempt(3),  # Stop after 3 attempts
    wait=wait_exponential(min=1, max=60),  # Exponential backoff
    retry=(lambda x: True),  # Always retry
)

# fmt: off
HTTP_4XX_STATUS_CODES = (401, 402, 403, 405, 406, 407, 408, 409, 410, 411, 412, 413, 414, 415, 416, 417, 418, 419,
                         420, 421, 422, 423, 424, 425, 426, 427, 428, 429, 431, 451)
# NOTE 400 and 404 is not included

HTTP_5XX_STATUS_CODES = (500, 501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511)
# fmt: on


class TransactionCoordinator:
    def __init__(self) -> None:
        self.client1, self.client2, self.client3 = self.get_clients()

    def get_hosts_from_cluster(self) -> list[str]:
        config = configparser.ConfigParser()
        config.read("cluster.ini")
        return [config["CLUSTER"][key] for key in config["CLUSTER"]]

    def get_clients(self) -> Iterator[APIClient]:
        return (APIClient(host) for host in self.get_hosts_from_cluster())

    async def create(self, group_id: str) -> Coroutine | bool | tuple:
        """Creates given groupId on all nodes."""
        post_responses = await asyncio.gather(
            self.client1.post(group_id),
            self.client2.post(group_id),
            self.client3.post(group_id),
            return_exceptions=True,  # Return exceptions instead of raising them
        )
        SUCCESS = True
        if all(
            isinstance(response, httpx.HTTPStatusError) and response.response.status_code == 400
            for response in post_responses
        ):
            # maybe log it no other action needed!
            # "EXCEPTION CASE == 400 | ALREADY EXISTS"
            return SUCCESS
        if all(
            isinstance(response, httpx.HTTPStatusError)
            and response.response.status_code in HTTP_4XX_STATUS_CODES + HTTP_5XX_STATUS_CODES
            for response in post_responses
        ):
            RETRY_TO_CREATE = True  # Needed bcz nothing created
            return RETRY_TO_CREATE
        if any(isinstance(response, httpx.HTTPStatusError) for response in post_responses) and any(
            isinstance(response, httpx.Response) and response.status_code == 201 for response in post_responses
        ):  # check if there is any exception
            # ROLLBACK NEEDED! AT LEAST ONE REQUEST CREATED AND AT LEAST ONE REQUEST FAILED
            return await self.response_processor(
                post_responses, expected_status_code=201, group_id=group_id, request_interface_come_from="POST"
            )  # proceed to rollback which means delete all
        return (
            SUCCESS
            if all(isinstance(response, httpx.Response) and response.status_code == 201 for response in post_responses)
            else not SUCCESS
        )  # heavily relies on 201 status code, if other 2XX codes are possible consider them

    async def delete(self, group_id: str) -> Coroutine | tuple | bool:
        """Deletes given groupId from all nodes."""
        delete_responses = await asyncio.gather(
            self.client1.delete(group_id),
            self.client2.delete(group_id),
            self.client3.delete(group_id),
            return_exceptions=True,  # Return exceptions instead of raising them
        )
        SUCCESS = True
        # return success all responses are 200, or 404 which means they are not in there
        # 404 means they are already deleted or not in there
        if all(
            isinstance(response, httpx.HTTPStatusError) and response.response.status_code == 404
            for response in delete_responses
        ):
            # "EXCEPTION CASE == 404 | COULDN'T FOUND. INTENDED OPERATION WAS DELETE THEM FROM ALL NODES"
            return SUCCESS
        if all(
            isinstance(response, httpx.HTTPStatusError)
            and response.response.status_code in (400,) + HTTP_4XX_STATUS_CODES + HTTP_5XX_STATUS_CODES
            for response in delete_responses
        ):
            RETRY_TO_CREATE = True  # Needed bcz nothing created
            return RETRY_TO_CREATE
        if any(isinstance(response, httpx.HTTPStatusError) for response in delete_responses) and any(
            isinstance(response, httpx.Response) and response.status_code == 200 for response in delete_responses
        ):  # check if there is any exception and if one of them at least is succeeded
            # ROLLBACK NEEDED! AT LEAST ONE REQUEST CREATED AND AT LEAST ONE REQUEST FAILED
            return await self.response_processor(
                delete_responses, expected_status_code=200, group_id=group_id, request_interface_come_from="DELETE"
            )  # proceed to rollback which means create them
        return delete_responses

    async def response_processor(
        self, post_responses: Any, expected_status_code: int, group_id: str, request_interface_come_from: str
    ) -> Any:
        success_clients = []
        for client, response in zip([self.client1, self.client2, self.client3], post_responses):
            if not isinstance(response, Exception) and response.status_code == expected_status_code:
                success_clients.append(client)

        if request_interface_come_from == "POST":
            # MAKE DELETE REQUESTS
            try:
                for attempt in retry_strategy:
                    with attempt:
                        rollback_responses = await asyncio.gather(
                            *(client.delete(group_id) for client in success_clients), return_exceptions=True
                        )
                        if all(
                            isinstance(response, httpx.Response) and response.status_code == 200
                            for response in rollback_responses
                        ):
                            # ALL SUCCESSFUL REQUESTS ARE ROLLED BACK
                            return True, "rollback success", "NOTHING CHANGED, REMAINS CONSISTENT"
            except RetryError:
                print("All rollback attempts failed. Registering it in a queue.", rollback_responses)
                # Error Reporting and Logging, Alerting and Monitoring.
                # Register the failure in a queue for later processing
                # queue.append((group_id, success_clients, intended operation, failed_state))
        elif request_interface_come_from == "DELETE":
            # MAKE POST REQUESTS
            try:
                for attempt in retry_strategy:
                    with attempt:
                        rollback_responses = await asyncio.gather(
                            *(client.post(group_id) for client in success_clients), return_exceptions=True
                        )
                        if all(
                            isinstance(response, httpx.Response) and response.status_code == 201
                            for response in rollback_responses
                        ):
                            # all successfull clients which are deleted successfully created back
                            ROLLBACK_SUCCESSFULL = True
                            return ROLLBACK_SUCCESSFULL, "rollback success"
                        elif all(
                            isinstance(response, httpx.HTTPStatusError) and response.response.status_code == 400
                            for response in rollback_responses
                        ):
                            ROLLBACK_SUCCESSFULL = True
                            return ROLLBACK_SUCCESSFULL, "rollback success | They are allready created"
            except RetryError:
                print("All rollback attempts failed. Registering it in a queue.", rollback_responses)
                # Error Reporting and Logging, Alerting and Monitoring.
                # Register the failure in a queue for later processing
                # queue.append((group_id, success_clients, intended operation, failed_state))
                return False

    async def coordinate(self) -> None:
        group_id = "4"
        await self.create(group_id)
