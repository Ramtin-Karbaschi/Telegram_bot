import sys, pathlib
# Ensure project root is in PYTHONPATH for 'services' package resolution
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from unittest.mock import patch, MagicMock

from services.crypto_payment_service import CryptoPaymentService, USDT_DECIMALS

WALLET = "TXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"  # fake wallet
TX_HASH = "abcdef123456" * 5  # 60 chars -> fake 60; tron hashes are 64, sufficient for mock
CONTRACT = "TETHER_CONTRACT"  # will be patched via config in service

@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    """Patch config values used inside service so tests don't depend on real env."""
    monkeypatch.setattr("config.TRONGRID_API_KEY", "test_key", raising=False)
    monkeypatch.setattr("config.USDT_TRC20_CONTRACT_ADDRESS", CONTRACT, raising=False)
    yield

def _build_event(to_address, amount):
    return {
        "event_name": "Transfer",
        "result": {
            "contract_address": CONTRACT,
            "to": to_address,
            "value": str(amount)
        }
    }

@patch("services.crypto_payment_service.requests.get")
@pytest.mark.parametrize("raw_amount, min_amount, expected_ok", [
    (1000 * 10 ** USDT_DECIMALS, 1000, True),            # exact amount
    (1500 * 10 ** USDT_DECIMALS, 1000, True),            # over payment
    (900 * 10 ** USDT_DECIMALS, 1000, False),            # under payment
])
def test_verify_payment_by_hash(mock_get, raw_amount, min_amount, expected_ok):
    # Build fake response
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [_build_event(WALLET, raw_amount)]}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    ok, amount = CryptoPaymentService.verify_payment_by_hash(TX_HASH, min_amount, WALLET)
    assert ok is expected_ok
    if expected_ok:
        assert amount >= min_amount
    else:
        assert amount == 0.0

@patch("services.crypto_payment_service.requests.get")
def test_verify_wrong_dest(mock_get):
    mock_resp = MagicMock()
    # to address different
    mock_resp.json.return_value = {"data": [_build_event("OTHER_ADDR", 2000)]}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    ok, amount = CryptoPaymentService.verify_payment_by_hash(TX_HASH, 1000, WALLET)
    assert not ok and amount == 0.0
