"""
Tiny JSON-RPC client for bitcoind.

Why not python-bitcoinrpc? We want JSON numbers parsed as Decimal so that the
BTC->satoshi conversion is exact (a float like 0.1 cannot be represented
precisely, which would corrupt the satoshi totals).
"""
from __future__ import annotations

import json
import os
from decimal import Decimal

import requests


class BitcoinRPC:
    def __init__(
        self,
        user: str | None = None,
        password: str | None = None,
        host: str = "127.0.0.1",
        port: int = 8332,
        timeout: int = 60,
    ):
        self.user = user or os.environ.get("BTC_RPC_USER", "")
        self.password = password or os.environ.get("BTC_RPC_PASSWORD", "")
        self.url = f"http://{host}:{port}"
        self.timeout = timeout
        self._id = 0
        self._session = requests.Session()
        self._session.auth = (self.user, self.password)
        self._session.headers.update({"content-type": "application/json"})

    def call(self, method: str, *params):
        self._id += 1
        payload = json.dumps(
            {"jsonrpc": "1.0", "id": self._id, "method": method, "params": list(params)}
        )
        resp = self._session.post(
            self.url,
            data=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        # parse_float=Decimal keeps BTC amounts exact
        data = json.loads(resp.text, parse_float=Decimal)
        if data.get("error"):
            raise RuntimeError(f"RPC error for {method}: {data['error']}")
        return data["result"]

    # ---- convenience wrappers -------------------------------------------
    def getblockcount(self) -> int:
        return int(self.call("getblockcount"))

    def getblockchaininfo(self) -> dict:
        return self.call("getblockchaininfo")

    def getblockhash(self, height: int) -> str:
        return self.call("getblockhash", height)

    def getblock(self, block_hash: str, verbosity: int = 2) -> dict:
        return self.call("getblock", block_hash, verbosity)


SATS_PER_BTC = Decimal(100_000_000)


def btc_to_sat(value) -> int:
    """Convert a BTC amount (Decimal preferred) to an integer number of satoshi."""
    return int((Decimal(value) * SATS_PER_BTC).to_integral_value())
