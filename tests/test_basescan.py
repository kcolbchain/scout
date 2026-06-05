import pytest
import aiohttp
from unittest.mock import patch, MagicMock, AsyncMock
from scout.backends.basescan import BasescanBackend

@pytest.mark.asyncio
async def test_basescan_fetch():
    backend = BasescanBackend(api_key="test_key")
    
    mock_response_data = {
        "status": "1",
        "message": "OK",
        "result": [
            {
                "hash": "0x123",
                "to": "0xabc",
                "timeStamp": "1620000000",
                "value": "1000000000000000000"
            }
        ]
    }
    
    # Mock aiohttp ClientSession
    mock_session = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = mock_response_data
    
    # Setup context managers
    mock_session.get.return_value.__aenter__.return_value = mock_resp
    
    with patch("aiohttp.ClientSession", return_value=mock_session):
        mock_session.__aenter__.return_value = mock_session
        activities = await backend.fetch("0xtest", "base")
        
        assert len(activities) == 1
        assert activities[0].tx_hash == "0x123"
        assert activities[0].chain == "base"
        assert activities[0].value_eth == 1.0

@pytest.mark.asyncio
async def test_basescan_fetch_wrong_chain():
    backend = BasescanBackend(api_key="test_key")
    activities = await backend.fetch("0xtest", "ethereum")
    assert len(activities) == 0
