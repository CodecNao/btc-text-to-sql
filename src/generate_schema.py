"""
Bonus (HW item 2a): auto-generate a SQL schema from a getblock JSON object.

Per the assignment's *recommended* approach, we do NOT ask the LLM to emit SQL
directly (non-deterministic / unverifiable). Instead this is plain code that
walks the JSON and infers column types. Nested arrays (tx, vin, vout) become
child tables linked by foreign keys. Run it once, eyeball the output, then
hand-tune (e.g. force money columns to INTEGER satoshi) -> that's the "99%
automatic, small human adjustment" the assignment describes.

Usage:
    python -m src.generate_schema sample_block.json > schema/auto_schema.sql
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal


def sql_type(value) -> str:
    if isinstance(value, bool):
        return "INTEGER"          # SQLite has no bool
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, (float, Decimal)):
        return "REAL"
    return "TEXT"                 # str, and JSON-encoded nested objects/arrays


def infer_columns(obj: dict) -> list[tuple[str, str]]:
    """Return (column_name, sql_type) for scalar / object fields of a dict."""
    cols = []
    for key, val in obj.items():
        if isinstance(val, list):
            continue              # arrays handled as child tables
        if isinstance(val, dict):
            # flatten one level: scriptPubKey.type -> script_pub_key_type
            for sub_k, sub_v in val.items():
                cols.append((f"{key}_{sub_k}".lower(), sql_type(sub_v)))
        else:
            cols.append((key.lower(), sql_type(val)))
    return cols


def emit_table(name: str, columns: list[tuple[str, str]], parent_fk: str | None) -> str:
    lines = [f"CREATE TABLE IF NOT EXISTS {name} ("]
    body = []
    if parent_fk:
        body.append(f"    {parent_fk} TEXT")
    for col, typ in columns:
        body.append(f"    {col} {typ}")
    lines.append(",\n".join(body))
    lines.append(");")
    return "\n".join(lines)


def generate(block: dict) -> str:
    out: list[str] = ["-- AUTO-GENERATED from a sample getblock JSON. Review before use.\n"]

    out.append(emit_table("blocks", infer_columns(block), parent_fk=None))

    tx_list = block.get("tx", [])
    if tx_list:
        tx = tx_list[0]
        out.append(emit_table("transactions", infer_columns(tx), parent_fk="block_hash"))
        if tx.get("vin"):
            out.append(emit_table("vin", infer_columns(tx["vin"][0]), parent_fk="txid"))
        if tx.get("vout"):
            out.append(emit_table("vout", infer_columns(tx["vout"][0]), parent_fk="txid"))

    return "\n\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m src.generate_schema <sample_block.json>")
    with open(sys.argv[1]) as f:
        block = json.load(f, parse_float=Decimal)
    print(generate(block))
