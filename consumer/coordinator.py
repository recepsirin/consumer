from __future__ import annotations

import asyncio
import configparser
from collections.abc import Iterator

import httpx
from tenacity import RetryError, Retrying, stop_after_attempt, wait_exponential

from consumer.client import APIClient

retry_strategy = Retrying(
    stop=stop_after_attempt(3),  # Stop after 3 attempts
    wait=wait_exponential(min=1, max=60),  # Exponential backoff
    retry=(lambda x: True),  # Always retry
)

http_4xx_status_codes = [
    401,
    402,
    403,
    405,
    406,
    407,
    408,
    409,
    410,
    411,
    412,
    413,
    414,
    415,
    416,
    417,
    418,
    419,
    420,
    421,
    422,
    423,
    424,
    425,
    426,
    427,
    428,
    429,
    431,
    451,
]  # NOTE 400 and 404 is not included

http_5xx_status_codes = [500, 501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511]


class TransactionCoordinator:
    def __init__(self):
        self.client1, self.client2, self.client3 = self.get_clients()

    def get_hosts_from_cluster(self) -> list[str]:
        config = configparser.ConfigParser()
        config.read("cluster.ini")
        return [config["CLUSTER"][key] for key in config["CLUSTER"]]

    def get_clients(self) -> Iterator[APIClient]:
        return (APIClient(host) for host in self.get_hosts_from_cluster())

    async def create(self, group_id: str):
        """Creates given groupId on all nodes."""
        post_responses = await asyncio.gather(
            self.client1.post(group_id),
            self.client2.post(group_id),
            self.client3.post(group_id),
            return_exceptions=True,  # Return exceptions instead of raising them
        )
        if all(
            isinstance(response, httpx.HTTPStatusError) and response.response.status_code == 400
            for response in post_responses
        ):
            # it is an edge case where groupId is already created on all nodes.
            # no rollback and retry needed bcz they are already created
            IS_ROLLBACK_NEEDED = False
            OPERATION_SUCCESS = False
            RETRY_TO_CREATE = False  # NO because they are already created
            return IS_ROLLBACK_NEEDED, OPERATION_SUCCESS, RETRY_TO_CREATE
        if all(
            isinstance(response, httpx.HTTPStatusError)
            and response.response.status_code in http_4xx_status_codes + http_5xx_status_codes
            for response in post_responses
        ):
            IS_ROLLBACK_NEEDED = False
            OPERATION_SUCCESS = False
            RETRY_TO_CREATE = True  # Needed bcz nothing created
            return IS_ROLLBACK_NEEDED, OPERATION_SUCCESS, RETRY_TO_CREATE
        if any(isinstance(response, Exception) for response in post_responses) and any(
            isinstance(response, httpx.Response) and response.status_code == 201 for response in post_responses
        ):  # check if there is any exception
            return await self.response_processor(
                post_responses, expected_status_code=201, group_id=group_id, request_interface_come_from="POST"
            )  # proceed to rollback which means delete all
        return post_responses

    async def delete(self, group_id: str):
        """Deletes given groupId from all nodes."""
        delete_responses = await asyncio.gather(
            self.client1.delete(group_id),
            self.client2.delete(group_id),
            self.client3.delete(group_id),
            return_exceptions=True,  # Return exceptions instead of raising them
        )
        # return success all responses are 200, or 404 which means they are not in there
        # 404 means they are already deleted or not in there
        if all(
            isinstance(response, httpx.HTTPStatusError) and response.response.status_code == 404
            for response in delete_responses
        ):
            print(
                "THEY ARE NOT IN THERE SO IT ASSUMES THEY ARE ALREADY DELETED SINCE "
                "THIS INTERFACE'S RESPONSIBILITY TO DELETE THEM FROM ALL NODES"
            )
            IS_ROLLBACK_NEEDED = False
            OPERATION_SUCCESS = False
            RETRY_TO_DELETE = False  # NO because they are already deleted
            return IS_ROLLBACK_NEEDED, OPERATION_SUCCESS, RETRY_TO_DELETE, "NOTHING FOUND TO BE DELETED"
        if all(isinstance(response, Exception) for response in delete_responses):
            print("none of the delete requests succeeded try again")
            print("if everything is failed what we are rolling back? nothing right, but retry to delete")
            IS_ROLLBACK_NEEDED = False
            OPERATION_SUCCESS = False
            RETRY_TO_DELETE = True
            return IS_ROLLBACK_NEEDED, OPERATION_SUCCESS, RETRY_TO_DELETE, "NOTHING SUCCEEDED, SHOULD BE RETRIED"
        if any(isinstance(response, Exception) for response in delete_responses) and any(
            isinstance(response, httpx.Response) and response.status_code == 200 for response in delete_responses
        ):  # check if there is any exception and if one of them at least is succeeded
            print("we have at least one successful request which should be rolled back!")
            return await self.response_processor(
                delete_responses, expected_status_code=200, group_id=group_id, request_interface_come_from="DELETE"
            )  # proceed to rollback which means create them
        return delete_responses  # print("All DELETE requests succeeded. No rollback needed.")

    async def response_processor(
        self, post_responses, expected_status_code, group_id, request_interface_come_from: str
    ):
        success_clients = []
        for client, response in zip([self.client1, self.client2, self.client3], post_responses):
            if not isinstance(response, Exception) and response.status_code == expected_status_code:
                success_clients.append(client)

        if request_interface_come_from == "POST":
            # MAKE DELETE REQUESTS
            print("success clients", success_clients)
            try:
                for attempt in retry_strategy:
                    with attempt:
                        rollback_responses = await asyncio.gather(
                            *(client.delete(group_id) for client in success_clients), return_exceptions=True
                        )
                        if all(
                            isinstance(response, httpx.Response)
                            and response.status_code
                            == 200  # 200 means the successful client requests are rolled back [DELETED]
                            for response in rollback_responses
                        ):
                            print(
                                "What we expect the success clients should be rollback via deleting",
                                rollback_responses,
                            )
                            ROLLBACK_SUCCESSFULL = True
                            return ROLLBACK_SUCCESSFULL, "rollback success"
            except RetryError:
                print("All rollback attempts failed. Registering it in a queue.", rollback_responses)
                pass  # Register the failure in a queue for later processing
                # queue.append((group_id, success_clients))
            else:
                print(
                    "Comes here when any break/Return condition succeeds."
                    " ROLLBACK Operation succeeded. Compensation transaction is successful."
                )
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
                            print("all successfull clients which are deleted successfully created back, break")
                            ROLLBACK_SUCCESSFULL = True
                            return ROLLBACK_SUCCESSFULL, "rollback success"
                        elif all(
                            isinstance(response, httpx.HTTPStatusError) and response.response.status_code == 400
                            for response in rollback_responses
                        ):
                            print("they already created break")
                            ROLLBACK_SUCCESSFULL = True
                            return ROLLBACK_SUCCESSFULL, "rollback success"
            except RetryError:
                print("All rollback attempts failed. Registering it in a queue.", rollback_responses)
                pass  # Register the failure in a queue for later processing
                # queue.append((group_id, success_clients))
            else:
                print(
                    "Comes here when any break condition succeeds. "
                    "ROLLBACK Operation succeeded. Compensation transaction is successful."
                )

    async def coordinate(self):
        group_id = "4"
        print(await self.delete(group_id), "final")


asyncio.run(TransactionCoordinator().coordinate())
