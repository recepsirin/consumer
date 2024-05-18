from __future__ import annotations

import httpx
import pytest
import respx

from consumer.client import APIClient


@pytest.mark.asyncio
async def test_get(api_client: APIClient) -> None:
    group_id = "123"
    with respx.mock(base_url="http://invalid.test-node") as respx_mock:
        mocked_url = respx_mock.get(f"/v1/group/{group_id}/").respond(status_code=200, json={"groupId": group_id})

        response = await api_client.get(group_id)

        assert response.status_code == 200
        assert response.json() == {"groupId": group_id}
        assert mocked_url.called


@pytest.mark.asyncio
async def test_post(api_client: APIClient) -> None:
    group_id = "123"
    with respx.mock(base_url="http://invalid.test-node") as respx_mock:
        mocked_url = respx_mock.post("/v1/group/").respond(status_code=201)

        response = await api_client.post(group_id)

        assert response.status_code == 201
        assert mocked_url.called


@pytest.mark.asyncio
async def test_delete(api_client: APIClient) -> None:
    group_id = "123"
    with respx.mock(base_url="http://invalid.test-node") as respx_mock:
        mocked_url = respx_mock.delete("/v1/group/").respond(status_code=200)

        response = await api_client.delete(group_id)

        assert response.status_code == 200
        assert mocked_url.called


@pytest.mark.asyncio
async def test_post_400(api_client: APIClient) -> None:
    group_id = "12"
    with respx.mock(base_url="http://invalid.test-node") as respx_mock:
        mocked_url = respx_mock.post("/v1/group/").respond(status_code=400, json={"detail": "The object exists."})

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await api_client.post(group_id)

        assert exc_info.value.response.status_code == 400
        assert exc_info.value.response.json() == {"detail": "The object exists."}
        assert mocked_url.called
