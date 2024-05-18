from __future__ import annotations

import asyncio
import configparser
from collections.abc import Iterator
from enum import Enum
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
HTTP_4XX_STATUS_CODES = [401, 402, 403, 405, 406, 407, 408, 409, 410, 411, 412, 413, 414, 415, 416, 417, 418, 419,
                         420, 421, 422, 423, 424, 425, 426, 427, 428, 429, 431, 451]
# NOTE 400 and 404 is not included

HTTP_5XX_STATUS_CODES = [500, 501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511]


# fmt: on


class TransactionState(Enum):
    SUCCEEDED = "succeeded"
    ROLLED_BACK = "rolled_back"
    TO_BE_RETRIED = "to_be_retried"
    FAILED = "failed"


class TransactionCoordinator:
    def __init__(self) -> None:
        self.client1, self.client2, self.client3 = self.get_clients()

    def get_hosts_from_cluster(self) -> list[str]:
        config = configparser.ConfigParser()
        config.read("cluster.ini")
        return [config["CLUSTER"][key] for key in config["CLUSTER"]]

    def get_clients(self) -> Iterator[APIClient]:
        return (APIClient(host) for host in self.get_hosts_from_cluster())

    def _verify_status_code_exceptions(self, responses: Any, status_codes: int | list[int]) -> bool:
        """
        Checks if all responses in the given list contain HTTP errors matching the provided status codes.

        :param responses: A list of responses to check.
        :param status_codes: An integer or a list of integers representing the status codes to match.
        :return: True if all responses contain an error with a matching status code, False otherwise.
        """
        status_codes_set = {status_codes} if isinstance(status_codes, int) else set(status_codes)
        return all(
            isinstance(response, httpx.HTTPStatusError) and response.response.status_code in status_codes_set
            for response in responses
        )

    def _check_responses_include_both_exceptions_and_successful_cases(
        self, responses: Any, verified_status_code: int
    ) -> bool:
        """
        Verifies if the given responses include both HTTP status errors and successful cases.
        This method checks if there exists at least one instance of an HTTP status error among the responses
        and at least one instance of a successful case (identified by a specific status code).

        :param responses (Any): A collection of responses to check. Can be a list, tuple, etc.
        :param verified_status_code (int): The status code indicating a successful response.

        :return: True if both types of responses exist, False otherwise.
        """
        has_error = any(isinstance(response, httpx.HTTPStatusError) for response in responses)
        has_success = any(
            isinstance(response, httpx.Response) and response.status_code == verified_status_code
            for response in responses
        )
        return has_error and has_success

    def _are_all_expected_responses(self, responses: Any, status_code: int) -> bool:
        """
        Check if all responses match the expected status code.
        :param responses (Any): An iterable containing HTTP responses to be checked.
        :param status_code (int): The expected HTTP status code to be matched.
        :return: True if all responses match the expected status code, False otherwise.
        """
        return all(
            isinstance(response, httpx.Response) and response.status_code == status_code for response in responses
        )

    async def create(self, group_id: str) -> Coroutine | TransactionState | tuple:
        """Creates given groupId on all nodes."""
        post_responses = await asyncio.gather(
            self.client1.post(group_id),
            self.client2.post(group_id),
            self.client3.post(group_id),
            return_exceptions=True,  # Return exceptions instead of raising them
        )
        if self._verify_status_code_exceptions(post_responses, 400):
            return TransactionState.SUCCEEDED  # already exists
        if self._verify_status_code_exceptions(post_responses, HTTP_4XX_STATUS_CODES + HTTP_5XX_STATUS_CODES):
            return TransactionState.TO_BE_RETRIED  # nothing created so retry
        if self._check_responses_include_both_exceptions_and_successful_cases(
            post_responses, 201
        ):  # check if there is any exception
            # ROLLBACK NEEDED! AT LEAST ONE REQUEST CREATED AND AT LEAST ONE REQUEST FAILED
            return await self.response_processor(
                post_responses, expected_status_code=201, group_id=group_id, request_interface_come_from="POST"
            )  # proceed to rollback which means delete all
        return (
            TransactionState.SUCCEEDED
            if self._are_all_expected_responses(post_responses, 201)
            else TransactionState.FAILED
        )
        # heavily relies on 201 status code, if other 2XX codes are possible consider them

    async def delete(self, group_id: str) -> Coroutine | tuple | TransactionState:
        """Deletes given groupId from all nodes."""
        delete_responses = await asyncio.gather(
            self.client1.delete(group_id),
            self.client2.delete(group_id),
            self.client3.delete(group_id),
            return_exceptions=True,  # Return exceptions instead of raising them
        )
        # return success all responses are 200, or 404 which means they are not in there
        # 404 means they are already deleted or not in there
        if self._verify_status_code_exceptions(delete_responses, 404):
            return TransactionState.SUCCEEDED  # COULDN'T FOUND. INTENDED OPERATION WAS DELETE THEM FROM ALL NODES
        if self._verify_status_code_exceptions(delete_responses, [400] + HTTP_4XX_STATUS_CODES + HTTP_5XX_STATUS_CODES):
            return TransactionState.TO_BE_RETRIED
        if self._check_responses_include_both_exceptions_and_successful_cases(delete_responses, 200):
            # ROLLBACK NEEDED! AT LEAST ONE REQUEST CREATED AND AT LEAST ONE REQUEST FAILED
            return await self.response_processor(
                delete_responses, expected_status_code=200, group_id=group_id, request_interface_come_from="DELETE"
            )  # proceed to rollback which means create them
        return (
            TransactionState.SUCCEEDED
            if self._are_all_expected_responses(delete_responses, 200)
            else TransactionState.FAILED
        )

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
                        if self._are_all_expected_responses(rollback_responses, 200):
                            # ALL SUCCESSFUL REQUESTS ARE ROLLED BACK
                            return TransactionState.ROLLED_BACK
            except RetryError:
                return TransactionState.FAILED
        elif request_interface_come_from == "DELETE":
            # MAKE POST REQUESTS
            try:
                for attempt in retry_strategy:
                    with attempt:
                        rollback_responses = await asyncio.gather(
                            *(client.post(group_id) for client in success_clients), return_exceptions=True
                        )
                        if self._are_all_expected_responses(rollback_responses, 201):
                            return TransactionState.ROLLED_BACK
                        elif self._verify_status_code_exceptions(rollback_responses, 400):
                            return TransactionState.ROLLED_BACK
            except RetryError:
                return TransactionState.FAILED

    async def coordinate(self) -> None:
        group_id = "4"
        await self.create(group_id)
