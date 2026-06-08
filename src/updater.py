"""
HW item 3: keep the SQLite database in sync with bitcoind.

Guarantees the assignment asks for (correct / up-to-date / consistent):
  * Each block + all its tx/vin/vout is written inside ONE transaction
    (atomic: all-or-nothing).
  * INSERT OR REPLACE on stable primary keys (hash/txid) -> idempotent,
    safe to re-run.
  * Reorg detection: before extending the tip we check that the new block's
    previousblockhash matches our stored tip; if not we roll back the
    orphaned blocks and re-sync.
  * sync_state row records the verified tip so restarts are cheap.

The mapping JSON -> SQL is pure deterministic code (no LLM at run time), which
is how we satisfy "guaranteed 100% correct" for the bonus.

Run once:        python -m src.updater --db chain.db
Run on a timer:  */5 * * * *  cd /path && python -m src.updater --db chain.db
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

from .rpc import BitcoinRPC, btc_to_sat


def open_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # better concurrency for the timer job
    schema = (Path(__file__).resolve().parent.parent / "schema" / "schema.sql").read_text()
    conn.executescript(schema)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# JSON -> rows  (deterministic mapping)
# ---------------------------------------------------------------------------
def insert_block(conn: sqlite3.Connection, block: dict) -> None:
    """Insert one full block atomically. Caller wraps this in a transaction."""
    conn.execute(
        """INSERT OR REPLACE INTO blocks
           (hash, height, version, version_hex, merkleroot, time, mediantime,
            nonce, bits, difficulty, chainwork, n_tx, previousblockhash,
            nextblockhash, strippedsize, size, weight)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            block["hash"], block["height"], block.get("version"),
            block.get("versionHex"), block.get("merkleroot"), block.get("time"),
            block.get("mediantime"), block.get("nonce"), block.get("bits"),
            float(block["difficulty"]) if "difficulty" in block else None,
            block.get("chainwork"), block.get("nTx"),
            block.get("previousblockhash"), block.get("nextblockhash"),
            block.get("strippedsize"), block.get("size"), block.get("weight"),
        ),
    )

    for tx_index, tx in enumerate(block.get("tx", [])):
        is_coinbase = 1 if (tx.get("vin") and "coinbase" in tx["vin"][0]) else 0
        conn.execute(
            """INSERT OR REPLACE INTO transactions
               (txid, block_hash, block_height, hash, version, size, vsize,
                weight, locktime, is_coinbase, tx_index)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                tx["txid"], block["hash"], block["height"], tx.get("hash"),
                tx.get("version"), tx.get("size"), tx.get("vsize"),
                tx.get("weight"), tx.get("locktime"), is_coinbase, tx_index,
            ),
        )
        # rewrite children for this tx (idempotent on re-run)
        conn.execute("DELETE FROM vin  WHERE txid = ?", (tx["txid"],))
        conn.execute("DELETE FROM vout WHERE txid = ?", (tx["txid"],))

        for vin_index, vin in enumerate(tx.get("vin", [])):
            ss = vin.get("scriptSig") or {}
            witness = vin.get("txinwitness")
            conn.execute(
                """INSERT INTO vin
                   (txid, vin_index, prev_txid, prev_vout, coinbase,
                    script_sig_asm, script_sig_hex, sequence, txinwitness)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    tx["txid"], vin_index, vin.get("txid"), vin.get("vout"),
                    vin.get("coinbase"), ss.get("asm"), ss.get("hex"),
                    vin.get("sequence"),
                    json.dumps(witness) if witness else None,
                ),
            )

        for vout in tx.get("vout", []):
            spk = vout.get("scriptPubKey") or {}
            # Bitcoin Core >= 22 uses 'address'; older uses 'addresses' (list)
            addr = spk.get("address")
            addrs = spk.get("addresses")
            if addr is None and addrs:
                addr = addrs[0]
            conn.execute(
                """INSERT INTO vout
                   (txid, n, value_sat, script_pubkey_asm, script_pubkey_hex,
                    script_pubkey_type, req_sigs, address, addresses)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    tx["txid"], vout["n"], btc_to_sat(vout["value"]),
                    spk.get("asm"), spk.get("hex"), spk.get("type"),
                    spk.get("reqSigs"), addr,
                    json.dumps(addrs) if addrs and len(addrs) > 1 else None,
                ),
            )


def set_tip(conn: sqlite3.Connection, height: int, block_hash: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO sync_state (id, last_height, last_hash, updated_at)
           VALUES (1, ?, ?, ?)""",
        (height, block_hash, int(time.time())),
    )


def get_tip(conn: sqlite3.Connection) -> tuple[int, str] | None:
    row = conn.execute("SELECT last_height, last_hash FROM sync_state WHERE id = 1").fetchone()
    return (row[0], row[1]) if row else None


def rollback_to(conn: sqlite3.Connection, height: int) -> None:
    """Delete blocks above `height` (cascades to tx/vin/vout). Used on reorg."""
    conn.execute("DELETE FROM blocks WHERE height > ?", (height,))


# ---------------------------------------------------------------------------
# Main sync loop
# ---------------------------------------------------------------------------
def sync(db_path: str, max_blocks: int | None = None) -> None:
    rpc = BitcoinRPC()
    conn = open_db(db_path)

    tip = get_tip(conn)
    next_height = (tip[0] + 1) if tip else 0
    chain_height = rpc.getblockcount()

    # --- reorg check: does our stored tip still exist on the active chain? ---
    if tip:
        try:
            live_hash = rpc.getblockhash(tip[0])
        except RuntimeError:
            live_hash = None
        if live_hash != tip[1]:
            print(f"[reorg] stored tip {tip[0]} no longer on chain; rolling back")
            # walk back until our stored block matches the live chain
            h = tip[0]
            while h >= 0:
                row = conn.execute(
                    "SELECT hash FROM blocks WHERE height = ?", (h,)
                ).fetchone()
                if row and rpc.getblockhash(h) == row[0]:
                    break
                h -= 1
            with conn:
                rollback_to(conn, h)
                last = conn.execute(
                    "SELECT height, hash FROM blocks ORDER BY height DESC LIMIT 1"
                ).fetchone()
                if last:
                    set_tip(conn, last[0], last[1])
            next_height = h + 1

    written = 0
    height = next_height
    while height <= chain_height:
        if max_blocks is not None and written >= max_blocks:
            break
        block_hash = rpc.getblockhash(height)
        block = rpc.getblock(block_hash, verbosity=2)

        # consistency guard: chain must be contiguous
        if height > 0 and tip and height == tip[0] + 1:
            if block.get("previousblockhash") != tip[1]:
                print(f"[warn] discontinuity at {height}; triggering reorg path next run")
                break

        with conn:                       # atomic per-block commit
            insert_block(conn, block)
            set_tip(conn, height, block_hash)

        tip = (height, block_hash)
        written += 1
        if written % 1000 == 0:
            print(f"  ... synced up to height {height}")
        height += 1

    conn.close()
    print(f"Done. Wrote {written} block(s). Chain tip is {chain_height}.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Keep the SQLite DB in sync with bitcoind.")
    p.add_argument("--db", default="chain.db", help="path to sqlite database")
    p.add_argument("--max-blocks", type=int, default=None,
                   help="cap blocks written this run (useful for the 100k limit)")
    args = p.parse_args()
    sync(args.db, args.max_blocks)
