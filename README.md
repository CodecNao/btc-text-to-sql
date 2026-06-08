# Bitcoin Text-to-SQL (INFO7500 HW3)

A pipeline that syncs a local `bitcoind` node into a SQLite database and answers
**natural-language questions** about Bitcoin by translating them to SQL with an
LLM.

```
bitcoind  ──RPC──▶  updater.py  ──▶  chain.db (SQLite)  ◀──  text_to_sql.py  ◀── "how many blocks?"
                    (deterministic                            (OpenAI -> SQL -> answer)
                     JSON→SQL mapping)
```

## Layout

| Path | HW item | What it is |
|------|---------|------------|
| `schema/schema.sql`        | 2 | Hand-tuned schema (blocks/transactions/vin/vout), money in **satoshi** |
| `src/generate_schema.py`   | 2a (bonus) | Deterministic JSON→SQL schema generator |
| `src/rpc.py`               | 1, 3 | JSON-RPC client (Decimal-safe BTC→sat) |
| `src/updater.py`           | 3 | Incremental sync: atomic, idempotent, reorg-aware |
| `scripts/sync_cron.sh`     | 3c | Cron wrapper (runs every few minutes, lock-protected) |
| `src/text_to_sql.py`       | 4 | NL question → SQL → answer (OpenAI) |
| `tests/test_cases.py`      | 5 | 12 reference test cases of varying difficulty |
| `tests/hard_cases.md`      | 6 | 3 cases the system fails (with correct vs wrong SQL) |
| `slides/hard_cases_slide.md` | 6b | Slide content for the three hard cases |

## Setup

```bash
pip install -r requirements.txt
```

### 1. Sync bitcoind (HW item 1)
Copy `bitcoin.conf.example` into your Bitcoin data dir, set a real
`rpcpassword`, keep `txindex=1`, then start the node:

```bash
bitcoind -daemon
bitcoin-cli getblockcount        # watch it climb
bitcoin-cli getblockchaininfo    # blocks / headers / verificationprogress
```

It syncs from genesis and keeps running, appending new blocks as they arrive.
The first ~100k blocks (2009–2011) are nearly empty, so disk use is small.

### 2–3. Build & keep the DB updated (HW items 2, 3)

```bash
export BTC_RPC_USER=bitcoinrpc
export BTC_RPC_PASSWORD=...        # same as bitcoin.conf

# one-off (cap at 100k blocks per the assignment's disk limit)
python -m src.updater --db chain.db --max-blocks 100000
```

Schedule it every 5 minutes (HW item 3c):

```bash
crontab -e
# */5 * * * * /abs/path/btc-text-to-sql/scripts/sync_cron.sh >> /abs/path/sync.log 2>&1
```

**Correctness guarantees (HW item 3d):** every block is written in a single
transaction (atomic); primary keys are `hash`/`txid` with `INSERT OR REPLACE`
(idempotent — safe to re-run); and on startup the updater checks its stored tip
against the live chain, rolling back orphaned blocks if a **reorg** happened.
The JSON→SQL mapping is plain deterministic code (no LLM at run time), which is
how the "guaranteed 100% correct" bonus is satisfied.

### 4. Ask questions (HW item 4)

```bash
export OPENAI_API_KEY=sk-...
python -m src.text_to_sql --db "$(pwd)/chain.db" "how many blocks are there?"
```

The system prompt describes the *task* (text-to-sql for bitcoind); the user
prompt is the live schema + this *instance* (the question). Generated SQL is
executed read-only (only `SELECT`/`WITH` allowed).

### 5. Tests

```bash
# print the reference answer for all 12 cases
python -m tests.test_cases --db "$(pwd)/chain.db"

# grade the LLM end-to-end against the reference SQL
python -m tests.test_cases --db "$(pwd)/chain.db" --with-llm
```

### 6. Hard cases
See `tests/hard_cases.md` and `slides/hard_cases_slide.md`. All three failures
share one root cause: the **UTXO graph is implicit** (`vin.prev_txid/prev_vout`
→ `vout.txid/n`), and the model struggles to traverse that edge — the same
class of difficulty as SpiderV2-hard.

## Bonus: auto-generate the schema (HW item 2a)

```bash
bitcoin-cli getblock $(bitcoin-cli getblockhash 100000) 2 > sample_block.json
python -m src.generate_schema sample_block.json > schema/auto_schema.sql
```

This gets you ~99% of the way. The small human adjustments the assignment
mentions: (a) pick PKs/FKs, (b) rename the collision where an input's own
`txid` clashes with the parent-tx FK (also `txid`), and (c) force `value`
(REAL BTC) to `value_sat` (INTEGER satoshi). The committed `schema/schema.sql`
is that hand-finished version.

## Notes / possible extensions (from the assignment)
- Ethereum + third-party pricing data
- Reject questions that can't be answered from the DB
- Chat UI + chart generation
