# Slide: Where Text-to-SQL Breaks on Bitcoin

## The limit we found: when the schema is not enough

Our system (gpt-5.1) handles complex UTXO graph traversal, recursive CTEs,
and multi-table aggregations correctly. It fails when the answer requires
knowledge or capabilities *outside* the schema.

---

### Case 1 — External knowledge: the Bitcoin pizza transaction
**Q:** In which block height was the famous Bitcoin pizza transaction?
- Correct: look up txid `a1075db5...` → **block 57043**
- System does: search for outputs with value = 10,000 BTC → **block 26817**
- Root cause: the txid is not derivable from the schema; the model falls back
  to a value-based heuristic that matches the wrong transaction

### Case 2 — Hex decoding: genesis block hidden message
**Q:** What is Satoshi's hidden message in the genesis block coinbase?
- Correct: retrieve hex coinbase field, decode to ASCII →
  **"The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"**
- System does: generates invalid SQL trying to decode hex in-database →
  **OperationalError: no such table: g**
- Root cause: SQLite has no hex-to-text function; the task requires a step
  outside of SQL entirely

### Case 3 — Timestamp semantics: blocks mined in 2011
**Q:** How many blocks were mined in the year 2011 (UTC)?
- Correct: `strftime('%s','2011-01-01')` → **3067**
- System does: adds `'utc'` modifier, shifting the boundary by timezone offset → **3011**
- Root cause: the `'utc'` modifier tells SQLite to treat input as *local time*
  and convert it, introducing a subtle 56-block error

---

## Takeaway
gpt-5.1 has mastered UTXO graph traversal — the classic hard case.
The new difficulty cliff is **schema completeness**:
any question requiring external knowledge, binary decoding, or
precise library-function semantics is where even a strong model fails.
