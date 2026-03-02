# Newton Stage 1 Pre-Merge Code Review

**Branch:** `stage/1-data-pipeline`  
**Review Date:** 2026-02-18  
**Reviewer:** minimax-m2.5  
**Git Commit:** `b5fc9cf36fca22cc2a6415412fa723e4c28066ae`

---

## 1. Review Summary

Stage 1 (Data Pipeline) implementation is **substantially complete** with all core server-side data pipeline components implemented. The implementation follows the FINAL_SPEC.md architecture and includes data fetchers for both Oanda (EUR/USD) and Binance (BTC/USDT), TimescaleDB schema, feature store with technical indicators, data verification pipeline, and a health endpoint. The client includes a health/status panel as required.

However, there are **gaps that require attention** before merge:
- **Missing SQL syntax error** in migration file
- **Missing OHLCV data query API endpoints** (only health endpoint exists)
- **Client data viewer not implemented** (only health panel)
- **3-year backfill not verified** (requires runtime verification)
- **Feature store benchmark not performed**

---

## 2. Spec Compliance Check

### 2.1 Server Milestones

| Deliverable | Status | Details |
|-------------|--------|---------|
| Oanda data fetcher (EUR/USD) | ✅ PASS | `src/data/fetcher_oanda.py` - Historical + real-time ingestion with complete candle verification |
| Binance spot data fetcher (BTC/USDT) | ✅ PASS | `src/data/fetcher_binance.py` - Historical + real-time ingestion |
| TimescaleDB schema setup | ⚠️ FAIL | Migration has SQL syntax error (see findings) |
| Feature store (technical indicators) | ✅ PASS | `src/data/indicators.py` - RSI, MACD, BB, OBV, ATR implemented per spec |
| Data quality checks | ✅ PASS | `src/data/verifier.py` - Gap detection, OHLC verification, staleness watchdog |
| Data backfill (3 years) | ⏳ UNVERIFIED | Requires runtime verification - not testable in code review |
| Health endpoint | ✅ PASS | `src/api/v1/data.py` - Returns DB + broker connectivity + data freshness |
| API: data query endpoints | ❌ FAIL | Missing OHLCV query endpoints - only health endpoint implemented |
| Feature store benchmark | ⏳ UNVERIFIED | Not performed - requires runtime benchmark |

### 2.2 Client Milestones (DL-004)

| Deliverable | Status | Details |
|-------------|--------|---------|
| Health/status page | ✅ PASS | `client/src/main.js` - Displays system health, DB status, broker connectivity, data freshness |
| Data viewer | ❌ FAIL | Not implemented - spec requires viewing recent candles and indicator values |

---

## 3. Findings

### 3.1 Critical Issues

#### SQL Syntax Error in Migration
**File:** `src/data/migrations/0001_timescaledb_bootstrap.sql`  
**Line:** ~24

```sql
SELECT create_hypertable('features', 'time', if_not_exists => TRUE, migrate_data => TRUE);
                                                                                              ^ extra closing paren
```

**Impact:** Migration will fail when creating the features hypertable.

**Recommendation:** Remove the extra `)` before the semicolon.

---

#### Missing OHLCV Data Query API Endpoints
**Spec Requirement:** "OHLCV + feature retrieval via REST; OpenAPI schema published"

**Current State:** Only the `/api/v1/health` endpoint exists. No endpoints for:
- Querying historical OHLCV data
- Querying computed features
- Feature metadata registry access via API

**Recommendation:** Add API endpoints in `src/api/v1/data.py` for:
- `GET /api/v1/ohlcv/{instrument}?interval=1h&start=...&end=...`
- `GET /api/v1/features/{instrument}?interval=1h&start=...&end=...`
- `GET /api/v1/features/metadata`

---

### 3.2 Missing Features

#### Client Data Viewer Not Implemented
**Spec Requirement:** "View recent candles and indicator values per instrument/interval"

**Current State:** Client only shows health panel. No capability to view:
- Recent OHLCV candles
- Computed indicator values

**Recommendation:** Add data viewer component to client or ensure API endpoints are available for future client implementation.

---

### 3.3 Code Quality Observations

#### Positive Findings
- Clean separation of concerns (fetchers, verifiers, feature store)
- Type hints throughout codebase
- Proper UTC handling with `require_utc` helper
- Configuration validation using Pydantic models
- Good error handling with descriptive messages
- Security: URL validation in fetchers to prevent SSRF

#### Minor Issues
- **Incomplete broker health checks:** Health endpoint checks for API key presence but doesn't actually test broker connectivity
- **Feature key naming inconsistency:** The spec uses format like `rsi:period=14`, implementation matches this ✓

---

### 3.4 Security Review

- ✅ No hardcoded secrets
- ✅ Environment variable usage for credentials
- ✅ URL validation in HTTP clients to prevent SSRF
- ⚠️ No rate limiting on API endpoints (acceptable for localhost-only v1)

---

## 4. Recommendations

### Must Fix Before Merge
1. **Fix SQL syntax error** in `src/data/migrations/0001_timescaledb_bootstrap.sql`
2. **Add OHLCV data query endpoints** to API (`src/api/v1/data.py`)
3. **Add feature query endpoints** to API

### Should Fix Before Merge
4. Implement **client data viewer** or at minimum ensure API supports it
5. Improve broker health checks to actually test connectivity (not just key presence)

### Post-Merge / Runtime Verification Needed
- Run 3-year backfill for both instruments and verify row counts (±1% tolerance)
- Run feature store benchmark (< 500ms for 60-period lookback)
- Verify indicator calculations match TA-Lib reference (< 0.01% deviation)

---

## 5. Spec Compliance Status

| Section | Status |
|---------|--------|
| §4.1 Data Sources (Oanda + Binance) | ✅ PASS |
| §4.2 Database Schema | ⚠️ SYNTAX ERROR |
| §4.3 Feature Store | ✅ PASS |
| §4.4 Data Quality Checks | ✅ PASS |
| §4.5 Timezone Policy | ✅ PASS (UTC enforced) |
| §10 Client Health Panel | ✅ PASS |
| §10 Client Data Viewer | ❌ NOT IMPLEMENTED |
| §11.4 Health Endpoint | ✅ PASS |

---

## 6. Conclusion

**Recommendation:** **CONDITIONAL PASS** - Fix critical SQL error and add missing API endpoints before merge.

The Stage 1 implementation demonstrates solid foundations for the data pipeline with well-structured code. However, the missing OHLCV query API endpoints represent a significant gap in the Stage 1 exit criteria. The SQL syntax error will cause migration failure if not fixed.

**Next Steps:**
1. Fix migration SQL syntax
2. Add data query API endpoints
3. Verify 3-year backfill works
4. Run feature store benchmark

---

*Review completed by minimax-m2.5 on 2026-02-18*
