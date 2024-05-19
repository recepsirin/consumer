from __future__ import annotations

import asyncio
import configparser
from collections.abc import Iterator
from enum import Enum
from typing import Any

import httpx
from tenacity import RetryError, Retrying, retry, retry_if_result, stop_after_attempt, wait_exponential

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
HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
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
        """Retrieves a list of hostnames from the cluster configuration file.
        :return list[str]: A list of hostnames extracted from the 'cluster.ini' file.
        """
        config = configparser.ConfigParser()
        config.read("cluster.ini")
        return [config["CLUSTER"][key] for key in config["CLUSTER"]]

    def get_clients(self) -> Iterator[APIClient]:
        """Constructs an iterator over APIClient instances for each host in the cluster.
        :return Iterator[APIClient]: An iterator over APIClient instances, each initialized with a hostname
        from the cluster configuration.
        """
        return (APIClient(host) for host in self.get_hosts_from_cluster())

    def _verify_status_code_exceptions(self, responses: Any, status_codes: int | list[int]) -> bool:
        """Checks if all responses in the given list contain HTTP errors matching the provided status codes.
        :param responses: A collection of responses to check.
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
        """Checks if there exists at least one instance of an HTTP status error among the responses
        and at least one instance of a successful case (identified by a specific status code).
        :param responses (Any): A collection of responses to check.
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
        """Check if all responses match the expected status code.
        :param responses (Any): A collection of responses to check.
        :param status_code (int): The expected HTTP status code to be matched.
        :return: True if all responses match the expected status code, False otherwise.
        """
        return all(
            isinstance(response, httpx.Response) and response.status_code == status_code for response in responses
        )

    async def create(self, group_id: str) -> TransactionState:
        """Creates given groupId on all nodes."""
        post_responses = await asyncio.gather(
            self.client1.post(group_id),
            self.client2.post(group_id),
            self.client3.post(group_id),
            return_exceptions=True,  # Return exceptions instead of raising them
        )
        if self._verify_status_code_exceptions(post_responses, HTTP_BAD_REQUEST):
            return TransactionState.SUCCEEDED  # already exists
        if self._verify_status_code_exceptions(post_responses, HTTP_4XX_STATUS_CODES + HTTP_5XX_STATUS_CODES):
            return TransactionState.TO_BE_RETRIED  # nothing created so retry
        if self._check_responses_include_both_exceptions_and_successful_cases(post_responses, HTTP_CREATED):
            # Rollback required; at least one operation succeeded while another failed.
            return await self.process_to_rollback(
                post_responses, expected_status_code=HTTP_CREATED, group_id=group_id, original_request_method="POST"
            )
        return (
            TransactionState.SUCCEEDED
            if self._are_all_expected_responses(post_responses, HTTP_CREATED)
            else TransactionState.FAILED
        )  # Heavily relies on 201 status code; consider other 2XX codes if applicable

    async def delete(self, group_id: str) -> TransactionState:
        """Deletes given groupId from all nodes."""
        delete_responses = await asyncio.gather(
            self.client1.delete(group_id),
            self.client2.delete(group_id),
            self.client3.delete(group_id),
            return_exceptions=True,  # Return exceptions instead of raising them
        )
        if self._verify_status_code_exceptions(delete_responses, HTTP_NOT_FOUND):
            return TransactionState.SUCCEEDED  # Not found; intended operation was to delete from all nodes.
        if self._verify_status_code_exceptions(
            delete_responses, [HTTP_BAD_REQUEST] + HTTP_4XX_STATUS_CODES + HTTP_5XX_STATUS_CODES
        ):
            return TransactionState.TO_BE_RETRIED
        if self._check_responses_include_both_exceptions_and_successful_cases(delete_responses, HTTP_OK):
            # Rollback required; at least one operation succeeded while another failed.
            return await self.process_to_rollback(
                delete_responses, expected_status_code=HTTP_OK, group_id=group_id, original_request_method="DELETE"
            )
        return (
            TransactionState.SUCCEEDED
            if self._are_all_expected_responses(delete_responses, HTTP_OK)
            else TransactionState.FAILED
        )

    async def process_to_rollback(  # type: ignore[return]
        self, responses: Any, expected_status_code: int, group_id: str, original_request_method: str
    ) -> TransactionState:
        """Processes the transaction rollback,
        implementing retries based on the defined strategy within the rollback process context.
        :param responses: Responses received from the transaction.
        :param expected_status_code: Expected status code for successful responses.
        :param group_id: ID of the group.
        :param original_request_method: HTTP method used in the original request ('POST' or 'DELETE').
        :return: State (TransactionState) of the transaction after rollback and retries.
        :raise ValueError: If the original request method is not 'POST' or 'DELETE'.
        """
        success_clients = []
        for client, response in zip([self.client1, self.client2, self.client3], responses):
            if not isinstance(response, Exception) and response.status_code == expected_status_code:
                success_clients.append(client)

        if original_request_method == "POST":  # Make DELETE requests for rollback
            try:
                for attempt in retry_strategy:
                    with attempt:
                        rollback_responses = await asyncio.gather(
                            *(client.delete(group_id) for client in success_clients), return_exceptions=True
                        )
                        if self._are_all_expected_responses(rollback_responses, HTTP_OK):
                            return TransactionState.ROLLED_BACK
            except RetryError:
                return TransactionState.FAILED
        elif original_request_method == "DELETE":  # Make POST requests for rollback
            try:
                for attempt in retry_strategy:
                    with attempt:
                        rollback_responses = await asyncio.gather(
                            *(client.post(group_id) for client in success_clients), return_exceptions=True
                        )
                        if self._are_all_expected_responses(rollback_responses, HTTP_CREATED):
                            return TransactionState.ROLLED_BACK
                        elif self._verify_status_code_exceptions(rollback_responses, HTTP_BAD_REQUEST):
                            return TransactionState.ROLLED_BACK
            except RetryError:
                return TransactionState.FAILED
        else:
            raise ValueError("Unregistered request method. Available methods: 'POST', 'DELETE'")

    @retry(
        stop=stop_after_attempt(3),
        retry=retry_if_result(lambda result: result in [TransactionState.TO_BE_RETRIED, TransactionState.FAILED]),
    )
    async def coordinate(self, group_id: str, action: str) -> TransactionState:
        """Coordinates a transaction for a specified group.
        :param group_id: The ID of the group. (str)
        :param action: The action to perform. Allowed actions: 'create', 'delete'. (str)
        :return: The final state of the transaction. (TransactionState)
        :raise: ValueError: If the provided action is not valid.
        """
        valid_actions = {"create", "delete"}
        if action not in valid_actions:
            raise ValueError("Invalid action. Allowed actions: 'create', 'delete'")

        if action == "create":
            return await self.create(group_id)
        else:
            return await self.delete(group_id)
