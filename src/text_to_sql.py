"""
HW item 4: answer natural-language questions against the bitcoin SQLite DB.

Inputs:
    * a natural-language question
    * an absolute path to the sqlite database

Flow:
    1. extract the live schema straight from the database
    2. system prompt = the TASK description (text->sql for bitcoind)
       user prompt   = schema + this specific QUESTION (the task instance)
    3. ask OpenAI for SQL
    4. execute it read-only and print both the SQL and the answer

Env:
    OPENAI_API_KEY   (required)
    OPENAI_MODEL     (optional, default gpt-5.1)

Usage:
    python -m src.text_to_sql --db /abs/path/chain.db "how many blocks are there?"
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3

from openai import OpenAI

SYSTEM_PROMPT = (
    "You are a SQL developer that is expert in Bitcoin and you answer natural "
    "language questions about the bitcoind database in a sqlite database. You "
    "always only respond with SQL statements that are correct."
)


def extract_schema(db_path: str) -> str:
    """Pull every CREATE TABLE/INDEX statement from the live database."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type IN ('table','index') AND sql IS NOT NULL "
            "ORDER BY type DESC"
        ).fetchall()
    finally:
        conn.close()
    return "\n".join(r[0] + ";" for r in rows)


def clean_sql(text: str) -> str:
    """Strip ```sql fences / stray prose the model might add."""
    text = re.sub(r"```(?:sql)?", "", text, flags=re.IGNORECASE).strip("` \n")
    return text.strip()


def generate_sql(question: str, schema: str, model: str | None = None) -> str:
    client = OpenAI()  # reads OPENAI_API_KEY from env
    model = model or os.environ.get("OPENAI_MODEL", "gpt-5.1")
    user_prompt = (
        f"Database schema:\n{schema}\n\n"
        f"Question: {question}\n\n"
        "Respond with a single SQLite query and nothing else."
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return clean_sql(resp.choices[0].message.content)


def run_query(db_path: str, sql: str):
    """Execute read-only. Refuse anything that isn't a SELECT/WITH query."""
    if not re.match(r"^\s*(SELECT|WITH)\b", sql, flags=re.IGNORECASE):
        raise ValueError(f"Refusing to run non-read query:\n{sql}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, cur.fetchall()
    finally:
        conn.close()


def answer(question: str, db_path: str, model: str | None = None) -> dict:
    schema = extract_schema(db_path)
    sql = generate_sql(question, schema, model)
    cols, rows = run_query(db_path, sql)
    return {"question": question, "sql": sql, "columns": cols, "rows": rows}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Natural language -> SQL over the bitcoin DB.")
    p.add_argument("question", help="natural language question (quote it)")
    p.add_argument("--db", required=True, help="absolute path to the sqlite database")
    p.add_argument("--model", default=None, help="OpenAI model (default env OPENAI_MODEL or gpt-5.1)")
    args = p.parse_args()

    result = answer(args.question, args.db, args.model)
    print("Q :", result["question"])
    print("SQL:", result["sql"])
    print("-" * 60)
    if result["columns"]:
        print(" | ".join(result["columns"]))
    for row in result["rows"]:
        print(" | ".join(str(v) for v in row))
