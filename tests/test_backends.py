import pytest
from aioresponses import aioresponses
from scout.backends.basescan import BasescanBackend

@pytest.mark.asyncio
async def test_basescan_fetch():
    backend = BasescanBackend(api_key="test_key")
    address = "0x123"
    chain = "base"
    
    with aioresponses() as m:
        # Mock txlist
        m.get(
            f"https://api.basescan.org/api?action=txlist&address={address}&apikey=test_key&endblock=99999999&module=account&offset=20&page=1&sort=desc&startblock=0",
            payload={
                "status": "1",
                "message": "OK",
                "result": [
                    {
                        "timeStamp": "1620000000",
                        "hash": "0xabc",
                        "to": "0xdef",
                        "value": "1000000000000000000"
                    }
                ]
            }
        )
        # Mock tokentx
        m.get(
            f"https://api.basescan.org/api?action=tokentx&address={address}&apikey=test_key&endblock=99999999&module=account&offset=20&page=1&sort=desc&startblock=0",
            payload={
                "status": "1",
                "message": "OK",
                "result": [
                    {
                        "timeStamp": "1620000001",
                        "hash": "0xdef",
                        "to": "0xabc",
                        "contractAddress": "0xtoken",
                        "value": "5000000"
                    }
                ]
            }
        )
        
        activities = await backend.fetch(address, chain)
        assert len(activities) == 2
        # Sort is desc by timestamp, so tokentx is first
        assert activities[0].tx_hash == "0xdef"
        assert activities[1].tx_hash == "0xabc"
        assert activities[1].value_eth == 1.0

@pytest.mark.asyncio
async def test_basescan_wrong_chain():
    backend = BasescanBackend(api_key="test_key")
    activities = await backend.fetch("0x123", "ethereum")
    assert len(activities) == 0
