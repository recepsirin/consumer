from __future__ import annotations

import httpx


class APIClient:
    RESOURCE = "v1/group"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    async def get(self, group_id: str) -> httpx.Response | httpx.HTTPStatusError:
        async with httpx.AsyncClient() as client:
            try:
                url = f"{self.base_url}/{self.RESOURCE}/{group_id}/"
                response = await client.get(url)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                return exc

    async def post(self, group_id: str) -> httpx.Response | httpx.HTTPStatusError:
        async with httpx.AsyncClient() as client:
            try:
                url = f"{self.base_url}/{self.RESOURCE}/"
                response = await client.post(url, json={"groupId": group_id})
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                return exc

    async def delete(self, group_id: str) -> httpx.Response | httpx.HTTPStatusError:
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/{self.RESOURCE}/"
                response = await client.request(method="DELETE", url=url, json={"groupId": group_id})
                response.raise_for_status()
                return response
        except httpx.HTTPStatusError as exc:
            return exc
