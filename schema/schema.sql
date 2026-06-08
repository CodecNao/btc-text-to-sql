-- Bitcoin Text-to-SQL : SQLite schema
-- Mirrors the JSON returned by  getblock <hash> 2  (verbosity = 2).
-- Money is stored as INTEGER satoshi (1 BTC = 100_000_000 sat) for exactness.
-- Hierarchy: block -> tx[] -> vin[] / vout[]

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- One row per block
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS blocks (
    hash               TEXT    PRIMARY KEY,   -- block hash (hex)
    height             INTEGER NOT NULL UNIQUE,
    version            INTEGER,
    version_hex        TEXT,
    merkleroot         TEXT,
    time               INTEGER,               -- unix epoch (block header time)
    mediantime         INTEGER,
    nonce              INTEGER,
    bits               TEXT,
    difficulty         REAL,
    chainwork          TEXT,
    n_tx               INTEGER,               -- nTx
    previousblockhash  TEXT,
    nextblockhash      TEXT,
    strippedsize       INTEGER,
    size               INTEGER,
    weight             INTEGER
);

CREATE INDEX IF NOT EXISTS idx_blocks_time   ON blocks(time);
CREATE INDEX IF NOT EXISTS idx_blocks_height ON blocks(height);

-- ---------------------------------------------------------------------------
-- One row per transaction
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    txid         TEXT PRIMARY KEY,
    block_hash   TEXT NOT NULL,
    block_height INTEGER,                     -- denormalised for fast filtering
    hash         TEXT,                        -- witness tx id (== txid for non-segwit)
    version      INTEGER,
    size         INTEGER,
    vsize        INTEGER,
    weight       INTEGER,
    locktime     INTEGER,
    is_coinbase  INTEGER NOT NULL DEFAULT 0,  -- 1 if first input is a coinbase
    tx_index     INTEGER,                     -- position within the block (0 = coinbase)
    FOREIGN KEY (block_hash) REFERENCES blocks(hash) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tx_block  ON transactions(block_hash);
CREATE INDEX IF NOT EXISTS idx_tx_height ON transactions(block_height);

-- ---------------------------------------------------------------------------
-- One row per transaction input
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vin (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    txid          TEXT NOT NULL,              -- the tx that owns this input
    vin_index     INTEGER NOT NULL,           -- ordinal position in the vin array
    prev_txid     TEXT,                       -- spent output's txid (NULL for coinbase)
    prev_vout     INTEGER,                    -- spent output's index   (NULL for coinbase)
    coinbase      TEXT,                       -- coinbase hex (NULL for normal inputs)
    script_sig_asm TEXT,
    script_sig_hex TEXT,
    sequence      INTEGER,
    txinwitness   TEXT,                       -- JSON array of witness hex strings
    FOREIGN KEY (txid) REFERENCES transactions(txid) ON DELETE CASCADE,
    UNIQUE (txid, vin_index)
);

CREATE INDEX IF NOT EXISTS idx_vin_txid     ON vin(txid);
CREATE INDEX IF NOT EXISTS idx_vin_prevtxid ON vin(prev_txid, prev_vout);

-- ---------------------------------------------------------------------------
-- One row per transaction output
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vout (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    txid                TEXT NOT NULL,
    n                   INTEGER NOT NULL,      -- output index within the tx
    value_sat           INTEGER NOT NULL,      -- value in SATOSHI (BTC * 1e8)
    script_pubkey_asm   TEXT,
    script_pubkey_hex   TEXT,
    script_pubkey_type  TEXT,                  -- pubkeyhash / scripthash / witness_v0_* ...
    req_sigs            INTEGER,
    address             TEXT,                  -- primary address (scriptPubKey.address)
    addresses           TEXT,                  -- JSON array when multiple (legacy multisig)
    FOREIGN KEY (txid) REFERENCES transactions(txid) ON DELETE CASCADE,
    UNIQUE (txid, n)
);

CREATE INDEX IF NOT EXISTS idx_vout_txid    ON vout(txid);
CREATE INDEX IF NOT EXISTS idx_vout_address ON vout(address);
CREATE INDEX IF NOT EXISTS idx_vout_type    ON vout(script_pubkey_type);

-- ---------------------------------------------------------------------------
-- Bookkeeping: lets the updater know where it left off and detect reorgs.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_state (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    last_height   INTEGER NOT NULL,
    last_hash     TEXT    NOT NULL,
    updated_at    INTEGER NOT NULL
);
