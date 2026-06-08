"""
HW item 5: >= 10 test cases of varying difficulty.

Each case is a triple:
    question  -> natural language question
    sql       -> a SQL statement that produces the correct answer
    note      -> what makes it easy/medium/hard

Run it against a populated DB to print the THIRD element of every triple
(the actual answer from executing on the db):

    python -m tests.test_cases --db /abs/path/chain.db

To grade the LLM end-to-end (compare model SQL result vs the reference SQL
result) add --with-llm  (needs OPENAI_API_KEY):

    python -m tests.test_cases --db /abs/path/chain.db --with-llm
"""
from __future__ import annotations

import argparse
import sqlite3

TEST_CASES = [
    # ---- easy: single table, single aggregate ----------------------------
    {
        "question": "How many blocks are there?",
        "sql": "SELECT COUNT(*) AS n_blocks FROM blocks;",
        "note": "easy / COUNT on one table",
    },
    {
        "question": "How many transactions are stored in total?",
        "sql": "SELECT COUNT(*) AS n_tx FROM transactions;",
        "note": "easy / COUNT",
    },
    {
        "question": "What is the highest block height we have?",
        "sql": "SELECT MAX(height) AS tip FROM blocks;",
        "note": "easy / MAX",
    },
    # ---- medium: ordering / filtering ------------------------------------
    {
        "question": "Which block has the most transactions? Give its height and tx count.",
        "sql": "SELECT height, n_tx FROM blocks ORDER BY n_tx DESC, height ASC LIMIT 1;",
        "note": "medium / ORDER BY + LIMIT",
    },
    {
        "question": "How many coinbase transactions are there?",
        "sql": "SELECT COUNT(*) AS n_coinbase FROM transactions WHERE is_coinbase = 1;",
        "note": "medium / boolean filter",
    },
    {
        "question": "What is the average number of transactions per block?",
        "sql": "SELECT AVG(n_tx) AS avg_tx_per_block FROM blocks;",
        "note": "medium / AVG",
    },
    # ---- aggregation across joins ----------------------------------------
    {
        "question": "What is the total value (in satoshi) of all outputs in block height 100000?",
        "sql": (
            "SELECT SUM(vo.value_sat) AS total_sat "
            "FROM vout vo "
            "JOIN transactions t ON t.txid = vo.txid "
            "WHERE t.block_height = 100000;"
        ),
        "note": "medium-hard / JOIN + SUM with filter",
    },
    {
        "question": "How many distinct output address types appear in the database?",
        "sql": "SELECT COUNT(DISTINCT script_pubkey_type) AS n_types FROM vout;",
        "note": "medium / COUNT DISTINCT",
    },
    {
        "question": "List the 5 largest single outputs ever seen, with their satoshi value and txid.",
        "sql": "SELECT txid, n, value_sat FROM vout ORDER BY value_sat DESC LIMIT 5;",
        "note": "medium / ORDER BY DESC LIMIT",
    },
    # ---- time handling ---------------------------------------------------
    {
        "question": "How many blocks were mined in the year 2011 (UTC)?",
        "sql": (
            "SELECT COUNT(*) AS n FROM blocks "
            "WHERE time >= strftime('%s','2011-01-01') "
            "AND time < strftime('%s','2012-01-01');"
        ),
        "note": "hard / unix-time -> calendar conversion",
    },
    {
        "question": "What was the total block reward outputs (coinbase outputs) summed in satoshi?",
        "sql": (
            "SELECT SUM(vo.value_sat) AS coinbase_out_sat "
            "FROM vout vo "
            "JOIN transactions t ON t.txid = vo.txid "
            "WHERE t.is_coinbase = 1;"
        ),
        "note": "hard / JOIN + filter on coinbase",
    },
    # ---- two-level aggregation -------------------------------------------
    {
        "question": "On the day with the most blocks mined, how many blocks were mined?",
        "sql": (
            "SELECT MAX(c) AS busiest_day_blocks FROM ("
            "  SELECT DATE(time,'unixepoch') AS d, COUNT(*) AS c "
            "  FROM blocks GROUP BY d);"
        ),
        "note": "hard / GROUP BY then aggregate over the groups",
    },
]


def run_reference(db_path: str):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    print(f"Running {len(TEST_CASES)} reference test cases against {db_path}\n")
    for i, tc in enumerate(TEST_CASES, 1):
        try:
            rows = conn.execute(tc["sql"]).fetchall()
            answer = rows[0] if len(rows) == 1 else rows
        except Exception as e:  # noqa: BLE001
            answer = f"ERROR: {e}"
        print(f"[{i:02d}] ({tc['note']})")
        print(f"   Q   : {tc['question']}")
        print(f"   SQL : {tc['sql']}")
        print(f"   ANS : {answer}\n")
    conn.close()


def run_with_llm(db_path: str):
    from src.text_to_sql import answer as llm_answer

    passed = 0
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    for i, tc in enumerate(TEST_CASES, 1):
        ref = conn.execute(tc["sql"]).fetchall()
        try:
            got = llm_answer(tc["question"], db_path)
            ok = got["rows"] == ref
        except Exception as e:  # noqa: BLE001
            got, ok = {"sql": f"ERROR: {e}", "rows": None}, False
        passed += ok
        print(f"[{i:02d}] {'PASS' if ok else 'FAIL'}  {tc['question']}")
        if not ok:
            print(f"      ref sql: {tc['sql']}")
            print(f"      llm sql: {got['sql']}")
            print(f"      ref/llm: {ref} != {got['rows']}")
    conn.close()
    print(f"\n{passed}/{len(TEST_CASES)} passed")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--with-llm", action="store_true",
                   help="also run the LLM and compare to the reference SQL")
    args = p.parse_args()
    if args.with_llm:
        run_with_llm(args.db)
    else:
        run_reference(args.db)
