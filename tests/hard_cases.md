# HW item 6 — Three "too hard" test cases (system fails)

Each case records the full required tuple:
1. the natural-language question
2. the **expected** SQL that produces the correct answer
3. the **expected** answer (from running the expected SQL)
4. the **incorrect** SQL the system currently generates
5. the **incorrect** answer (from running that SQL)

---

## Case 1 — External knowledge required: the Bitcoin pizza transaction

**1. Question:** "In which block height was the famous Bitcoin pizza transaction included? (The transaction where 10,000 BTC was paid for two pizzas)"

**2. Expected SQL** — must know the specific txid from outside the DB:
```sql
SELECT block_height
FROM transactions
WHERE txid = 'a1075db55d416d3ca199f55b6084e2115b9345e16c5cf302fc80e9d5fbf5d48d';
```

**3. Expected answer:** `block_height = 57043`

**4. Incorrect SQL the system generates** — guesses the transaction by value (10,000 BTC = 1,000,000,000,000 satoshi) instead of using the known txid:
```sql
SELECT b.height
FROM transactions t
JOIN vout o ON t.txid = o.txid
JOIN blocks b ON t.block_hash = b.hash
WHERE o.value_sat = 1000000000000
ORDER BY b.height
LIMIT 1;
```

**5. Incorrect answer:** `26817`

**Why it's hard:** the question contains domain-specific knowledge (the txid) that is *not in the schema*. The model cannot infer the txid from the natural-language description alone and falls back to a value-based heuristic that matches the wrong transaction.

---

## Case 2 — Requires hex parsing: genesis block hidden message

**1. Question:** "What is the hidden text message embedded by Satoshi Nakamoto in the genesis block's coinbase input?"

**2. Expected SQL** — the coinbase hex must be decoded to ASCII; SQLite has no built-in hex-to-text function, so the best we can do is return the raw hex:
```sql
SELECT coinbase
FROM vin
WHERE txid IN (
    SELECT txid FROM transactions WHERE block_height = 0
);
```
Then decode manually:
`04ffff001d0104455468652054696d65732030332f4a616e2f32303039204368616e63656c6c6f72206f6e206272696e6b206f66207365636f6e64206261696c6f757420666f722062616e6b73`
→ **"The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"**

**3. Expected answer:** `"The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"`

**4. Incorrect SQL the system generates** — attempts to use a non-existent table or function to decode hex:
```sql
SELECT CAST(X'...' AS TEXT) FROM genesis_block ...
-- results in: OperationalError: no such table: g
```

**5. Incorrect answer:** `OperationalError: no such table: g`

**Why it's hard:** answering requires two steps — (1) retrieve the raw hex coinbase field, and (2) decode that hex to ASCII text. SQLite has no `hex_to_text()` function, so the task is impossible to complete fully in a single SQL statement. The model generates syntactically invalid SQL when attempting the decode step.

---

## Case 3 — Timestamp edge case: blocks mined in 2011 (UTC)

**1. Question:** "How many blocks were mined in the year 2011 (UTC)?"

**2. Expected SQL:**
```sql
SELECT COUNT(*) AS n
FROM blocks
WHERE time >= strftime('%s','2011-01-01')
  AND time < strftime('%s','2012-01-01');
```

**3. Expected answer:** `3067`

**4. Incorrect SQL the system generates** — adds a redundant `'utc'` modifier to `strftime`, which causes SQLite to treat the input timestamp as local time and convert it, shifting the boundary:
```sql
SELECT COUNT(*) AS blocks_2011
FROM blocks
WHERE time >= strftime('%s', '2011-01-01 00:00:00', 'utc')
  AND time <  strftime('%s', '2012-01-01 00:00:00', 'utc');
```

**5. Incorrect answer:** `3011` (off by 56 blocks)

**Why it's hard:** `strftime('%s', 'YYYY-MM-DD')` in SQLite already treats the date string as UTC. Adding `'utc'` as a third modifier tells SQLite to interpret the input as *local time* and convert it to UTC, effectively shifting the boundary by the local timezone offset. The model adds the modifier believing it makes the query more explicit, but it introduces a subtle off-by-timezone-offset error that is hard to detect without running against real data.

---

### Common theme
All three failures share one root: **the schema alone is insufficient**.
- Case 1: the correct answer requires a specific transaction ID that exists only in external knowledge.
- Case 2: the correct answer requires decoding hex data — a capability SQL does not have.
- Case 3: the correct answer requires precise knowledge of SQLite's `strftime` UTC modifier semantics, which even an expert model misapplies.
