# MVP SPEC — Coordinated Fresh Capital Flow Strategy

## Strategy Idea

The system does not search for “smart wallets by identity”.
It searches for **coordinated fresh capital behavior**.

Core idea:

- new or nearly new capital appears
- several addresses accumulate in a synchronized way
- they concentrate into one token
- they do not immediately distribute to CEX
- later the market confirms the setup
- eventually distribution may begin, creating exit or short-watch conditions

The edge is in **behavior**, not in public labels.

---

## Core Layers

### 1. Fresh Wallet Layer
Select fresh or low-history addresses, but not all of them.

A fresh address candidate should show:

- recent meaningful funding
- quick move into one token after funding
- non-service behavior
- no immediate chaotic spread across many tokens

### 2. Funding Graph Layer
Even if the wallet is new, its capital came from somewhere.

Watch:

- who funded it
- route patterns
- similar funding sources
- time clustering

A stronger signal exists when several fresh addresses are funded in similar ways and then move into the same token.

### 3. Coordination Layer
Core dimensions of coordination:

- time similarity
- route similarity
- target-token similarity
- relative size similarity

The goal is to identify an unknown but coordinated cohort.

### 4. Token Absorption Layer
Determine whether the cohort is actually absorbing supply.

Signs:

- rising share of net inflow from the fresh group
- controlled holder growth
- low sell-back
- no fast CEX leakage
- price not yet fully reflecting the absorption

### 5. Public Confirmation Layer
The setup becomes tradable when the market starts confirming it.

Signs:

- breakout from base
- volume growth
- holder growth
- attention/catalyst increase if available
- early cohort still not broadly distributing

---

## Core Entities

The MVP works with:

- address
- funding event
- token trade
- cohort
- token window
- token state
- alert

---

## Fresh Address Rules

An address is considered fresh if all are true:

- `address_age_days <= 30`
- `previous_tx_count <= 20`
- `distinct_tokens_before_window <= 10`
- not labeled as exchange / bridge / router / treasury / service

---

## Cohort Formation Rules

Addresses belong to the same cohort if they satisfy at least **3 of 5**:

1. funding happened within the cohort funding window
2. source type or source cluster similarity
3. first buy of the same token happened within the buy window
4. first allocation size similarity within allowed deviation
5. same chain + DEX/router family similarity

A cohort is valid only if:

- `cohort_size >= 3`
- `fresh_ratio >= 0.5`

---

## Time Windows

Use:

- 15m
- 1h
- 6h
- 24h

Purpose:

- 15m → synchronization
- 1h → early impulse
- 6h → main detector window
- 24h → confirmation / regime monitoring

---

## Thresholds

### Fresh / Cohort
- `FRESH_MAX_AGE_DAYS = 30`
- `FRESH_MAX_PREV_TX = 20`
- `FRESH_MAX_DISTINCT_TOKENS = 10`
- `COHORT_MIN_SIZE = 3`
- `COHORT_MIN_FRESH_RATIO = 0.5`
- `COHORT_FUNDING_WINDOW_MIN = 180`
- `COHORT_BUY_WINDOW_MIN = 240`
- `SIZE_SIMILARITY_PCT = 35`

### Accumulation
- `MIN_COHORT_FUNDING_USD = 25000`
- `MIN_BUYERS = 3`
- `MAX_SYNC_BUY_SPREAD_MIN = 240`
- `MIN_TOKEN_CONCENTRATION = 0.45`
- `MIN_BUY_SELL_RATIO = 2.5`
- `MAX_SELL_BACK_PCT = 0.15`
- `MIN_LIQ_USD = 150000`
- `MIN_VOL_24H = 300000`
- `MAX_SLIPPAGE_TEST = 0.02`
- `ACC_SCORE_THRESHOLD = 70`

### Confirmation
At least 2 of 4:
- `PRICE_CONFIRM_PCT = 0.08`
- `VOLUME_CONFIRM_MULT = 1.8`
- `HOLDER_GROWTH_PCT = 0.05`
- `MAX_COHORT_BALANCE_DROP_CONFIRM = 0.10`

### Distribution
- `MIN_REDUCERS_RATIO = 0.30`
- `MIN_BALANCE_DROP_PCT = 0.12`
- `MIN_EXCHANGE_OUTFLOW_USD = 20000`
- `MIN_SELL_BUY_RATIO = 1.25`
- `DIST_SCORE_THRESHOLD = 65`

### Short Watch
- `SHORT_WATCH_DIST_SCORE_THRESHOLD = 75`

---

## Anti-Noise / Anti-Fake Rules

Block or penalize cases such as:

- service-like activity
- exchange-like churn
- bridge churn only
- treasury reshuffles
- airdrop farming chaos
- illiquid trash tokens
- already-vertical tokens before first alert
- immediate CEX leakage
- one address dominating >70% of cohort behavior

---

## Accumulation Feature Set

Need raw features like:

- fresh_count
- cohort_count
- coordinated_buyers
- funding_usd
- token_concentration
- net_buy_usd
- buy_sell_ratio
- sell_back_pct
- exchange_outflow_usd
- liq_usd
- vol_24h
- service_noise_score
- sync_buy_spread_min

---

## Accumulation Score

`acc_score = 0.25*funding + 0.25*coordination + 0.20*concentration + 0.20*absorption + 0.10*tradability`

All subscores normalized to `0..100`.

A token can become `fresh_accumulation` only if:

- hard threshold gates pass
- no anti-noise block
- `acc_score >= 70`

---

## Confirmation Rule

A prior fresh accumulation becomes confirmed if, within 1h–24h, at least **2 of 4** are true:

- `price_change_pct >= 0.08`
- `volume_multiple >= 1.8`
- `holders_growth_pct >= 0.05`
- `cohort_balance_drop <= 0.10`

---

## Distribution Feature Set

Need raw features like:

- reducers_ratio
- aggregate_balance_drop_pct
- exchange_outflow_usd
- sell_buy_ratio
- weak price context / price divergence

---

## Distribution Score

`dist_score = 0.35*reduction + 0.25*exchange_pressure + 0.20*sell_pressure + 0.20*price_divergence`

A token becomes `distribution_started` only if:

- prior accumulation context exists
- hard threshold gates pass
- `dist_score >= 65`

---

## Short Watch Rule

A token becomes `short_watch` only if:

- prior accumulation/confirmation exists
- distribution already started
- `dist_score >= 75`
- token is shortable
- short liquidity pass
- no squeeze-risk block

Examples of squeeze-risk block:

- borrow unavailable
- dangerous funding rate
- too-thin OI/liquidity profile
- active bullish catalyst still strengthening

---

## Token State Machine

Allowed states:

- `idle`
- `fresh_accumulation`
- `accumulation_confirmed`
- `distribution_started`
- `short_watch`
- `invalidated`

Allowed transitions:

- `idle -> fresh_accumulation`
- `fresh_accumulation -> accumulation_confirmed`
- `fresh_accumulation -> invalidated`
- `accumulation_confirmed -> distribution_started`
- `distribution_started -> short_watch`
- `distribution_started -> invalidated`

---

## Alert Types

Only 5 alert types are allowed in MVP:

- `FRESH_ACCUMULATION`
- `ACCUMULATION_CONFIRMED`
- `DISTRIBUTION_STARTED`
- `SHORT_WATCH`
- `INVALIDATION`

Each alert must include:

- unique id
- token
- chain
- alert_type
- severity
- score
- window_start
- window_end
- dedup_key
- payload_json
- sent flag
- timestamps

---

## Storage / Models Needed

Need structures or schemas for:

- addresses
- address_funding_events
- address_token_trades
- token_market_snapshots
- cohorts
- cohort_members
- cohort_token_positions
- token_detection_features
- alerts
- token_state

Start simple.
Repository abstraction + JSON/JSONL is acceptable for MVP.

---

## MVP Build Order

1. Core domain models, enums, config thresholds, validation helpers
2. Fresh address classifier
3. Funding normalization and feature extraction
4. Cohort builder
5. Token concentration engine
6. Accumulation feature calculator
7. Accumulation scoring and detector
8. Confirmation detector
9. Distribution detector
10. Short-watch detector
11. Token state machine
12. Alert engine
13. Pipeline orchestration
14. Artifacts and regression fixtures
15. CLI / Telegram-style alert summaries

---

## MVP Philosophy

This is not a magic predictor.
It is an operational detection pipeline.

The expected output is:

- which tokens are being accumulated by coordinated fresh cohorts
- which setups got confirmed
- where distribution began
- where short-watch conditions exist
- which setups are invalidated and should be ignored

Prefer:

- simple
- deterministic
- auditable
- testable
- provider-agnostic
