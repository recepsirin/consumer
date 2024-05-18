import httpx
import pytest
import respx

from consumer.client import APIClient


@pytest.mark.asyncio
async def test_full_lifecycle(api_client: APIClient) -> None:
    group_id = "14"
    with respx.mock(base_url="http://invalid.test-node") as respx_mock:
        create_group = respx_mock.post("/v1/group/").respond(status_code=201)
        # Create
        create_response = await api_client.post(group_id)
        assert create_response.status_code == 201
        assert create_group.called

        # Read
        read_group = respx_mock.get(f"/v1/group/{group_id}/").respond(status_code=200, json={"groupId": group_id})
        read_response = await api_client.get(group_id)
        assert read_response.status_code == 200
        assert read_response.json() == {"groupId": group_id}
        assert read_group.called

        # Delete
        delete_group = respx_mock.delete("/v1/group/").respond(status_code=200)
        delete_response = await api_client.delete(group_id)
        assert delete_response.status_code == 200
        assert delete_group.called

        # After the group is deleted, it is expected to have a 404
        read_group_404 = respx_mock.get(f"/v1/group/{group_id}/").respond(status_code=404, json={"groupId": group_id})
        read_response = await api_client.get(group_id)
        assert read_response.response.status_code == 404
        assert isinstance(read_response, httpx.HTTPStatusError)
        assert read_group_404.called
