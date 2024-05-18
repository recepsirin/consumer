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

        response_err = await api_client.post(group_id)

        assert response_err.response.status_code == 400
        assert response_err.response.json() == {"detail": "The object exists."}
        assert isinstance(response_err, httpx.HTTPStatusError)
        assert mocked_url.called


@pytest.mark.asyncio
async def test_get_404(api_client: APIClient) -> None:
    group_id = "123"
    with respx.mock(base_url="http://invalid.test-node") as respx_mock:
        mocked_url = respx_mock.get(f"/v1/group/{group_id}/").respond(status_code=404)

        response_err = await api_client.get(group_id)

        assert response_err.response.status_code == 404
        assert isinstance(response_err, httpx.HTTPStatusError)
        assert mocked_url.called
