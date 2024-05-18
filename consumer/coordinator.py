from __future__ import annotations

import asyncio
import configparser
from collections.abc import Iterator

import httpx

from consumer.client import APIClient


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
        print("Line 38 post_responses", post_responses)
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
            isinstance(response, httpx.HTTPStatusError) and response.response.status_code == 404
            for response in
            # it can be extendable with possible 4XX status
            post_responses
        ):
            # it is an edge case where groupId is already created on all nodes.
            # no rollback and retry needed bcz they are already created
            IS_ROLLBACK_NEEDED = False
            OPERATION_SUCCESS = False
            RETRY_TO_CREATE = True  # Needed bcz nothing created
            return IS_ROLLBACK_NEEDED, OPERATION_SUCCESS, RETRY_TO_CREATE
        if any(isinstance(response, Exception) for response in post_responses):  # check if there is any exception
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
        print("Line 66 delete_responses", delete_responses)
        if all(
            isinstance(response, httpx.HTTPStatusError) and response.response.status_code == 404
            for response in delete_responses
        ):
            print(
                "THEY ARE NOT IN THERE SO IT ASSUMES THEY ARE ALREADY DELETED "
                "SINCE THIS INTERFACE'S RESPONSIBILITY TO DELETE THEM FROM ALL NODES"
            )
            IS_ROLLBACK_NEEDED = False
            OPERATION_SUCCESS = False
            RETRY_TO_DELETE = False  # NO because they are already deleted
            return IS_ROLLBACK_NEEDED, OPERATION_SUCCESS, RETRY_TO_DELETE, "NOTHING FOUND TO BE DELETED"
        """if all(response.response.status_code == 200 for response in delete_responses):
        # MAYBE DUPLICATED LOGIC? CHECK IT AGAIN
            IS_ROLLBACK_NEEDED = False
            OPERATION_SUCCESS = True
            RETRY_TO_DELETE = False
            return IS_ROLLBACK_NEEDED, OPERATION_SUCCESS, RETRY_TO_DELETE, "OPERATION IS SUCCEEDED""" ""
        if any(isinstance(response, Exception) for response in delete_responses) and any(
            isinstance(response, httpx.Response) and response.status_code == 200 for response in delete_responses
        ):  # check if there is any exception and if one of them at least is succeeded
            print("we have at least one successful request which should be rolled back!")
            return await self.response_processor(
                delete_responses, expected_status_code=200, group_id=group_id, request_interface_come_from="DELETE"
            )  # proceed to rollback which means create them
        if all(isinstance(response, Exception) for response in delete_responses):
            print("none of the delete requests succeeded try again")
            print("if everything is failed what we are rolling back? nothing right")
            IS_ROLLBACK_NEEDED = False
            OPERATION_SUCCESS = False
            RETRY_TO_DELETE = True
            return IS_ROLLBACK_NEEDED, OPERATION_SUCCESS, RETRY_TO_DELETE, "NOTHING SUCCEEDED, SHOULD BE RETRIED"
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
            print("request interface POST")
            print("success clients", success_clients)
            rollback_responses = await asyncio.gather(
                *(client.delete(group_id) for client in success_clients), return_exceptions=True
            )
            print(rollback_responses, "LINE 76")
            if all(
                isinstance(response, httpx.Response) and response.status_code == 200
                # 200 means the successful client requests are rolled back
                for response in rollback_responses
            ):
                print(
                    "Line 95 rollback responses. What we expect the success clients should be rollback via deleting",
                    rollback_responses,
                )
                ROLLBACK_SUCCESSFULL = True
                return ROLLBACK_SUCCESSFULL, "rollback success"
                # break
            """
            elif all(isinstance(response, httpx.HTTPStatusError) and
             response.response.status_code == 404 for response in rollback_responses):
                print("they already deleted or could not found")
                # API DOC didn't mention about 404, but it's good to cover anyway.OR It is deleted.
                print("these successfull client couldn't get rolled back", rollback_responses)
                # register these clients addresses with the operation to the queue
                return "some clients are pushed into the queue to delete for rollback purposes"
                #break"""

        elif request_interface_come_from == "DELETE":
            # MAKE POST REQUESTS
            print("success client for DELETE INT", success_clients)
            rollback_responses = await asyncio.gather(
                *(client.post(group_id) for client in success_clients), return_exceptions=True
            )
            print("rollback_responses", rollback_responses, "DELETE INTERFACE", expected_status_code)
            if all(
                isinstance(response, httpx.Response) and response.status_code == 201 for response in rollback_responses
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

    async def coordinate(self):
        group_id = "4"
        print(await self.delete(group_id), "final")


asyncio.run(TransactionCoordinator().coordinate())
