"""Tests for tokenizer and classification vocabulary (T-203)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.analysis.tokenizer import (
    ClassificationRule,
    TokenSet,
    load_classifications,
    tokenize,
)

BASE_TIME = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


# ── Helpers ────────────────────────────────────────────────────────


def _write_classifications(tmp_path: Path, rules: list[dict]) -> str:
    path = tmp_path / "test_classifications.json"
    path.write_text(json.dumps({"tokens": rules}))
    return str(path)


def _make_rule(
    token: str,
    feature_key: str,
    condition: str,
    *,
    threshold: float | None = None,
    reference_key: str | None = None,
) -> ClassificationRule:
    return ClassificationRule(
        token=token,
        feature_key=feature_key,
        condition=condition,
        threshold=threshold,
        reference_key=reference_key,
    )


# ── Load classifications ──────────────────────────────────────────


class TestLoadClassifications:
    def test_load_valid(self, tmp_path: Path) -> None:
        rules_data = [
            {
                "token": "TEST_RSI14_CL_BLW_30",
                "feature_key": "rsi:period=14",
                "condition": "below",
                "threshold": 30,
            }
        ]
        path = _write_classifications(tmp_path, rules_data)
        rules = load_classifications(path)
        assert len(rules) == 1
        assert rules[0].token == "TEST_RSI14_CL_BLW_30"
        assert rules[0].feature_key == "rsi:period=14"
        assert rules[0].condition == "below"
        assert rules[0].threshold == 30.0
        assert rules[0].reference_key is None

    def test_load_with_reference_key(self, tmp_path: Path) -> None:
        rules_data = [
            {
                "token": "TEST_BB2020_CL_ABV_UPR",
                "feature_key": "_close",
                "condition": "above_ref",
                "reference_key": "bb:period=20,std=2.0:upper",
            }
        ]
        path = _write_classifications(tmp_path, rules_data)
        rules = load_classifications(path)
        assert len(rules) == 1
        assert rules[0].reference_key == "bb:period=20,std=2.0:upper"
        assert rules[0].threshold is None

    def test_load_multiple_rules(self, tmp_path: Path) -> None:
        rules_data = [
            {"token": "T1", "feature_key": "rsi:period=14", "condition": "below", "threshold": 30},
            {"token": "T2", "feature_key": "rsi:period=14", "condition": "above", "threshold": 70},
        ]
        path = _write_classifications(tmp_path, rules_data)
        rules = load_classifications(path)
        assert len(rules) == 2

    def test_load_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_classifications("/nonexistent/path.json")

    def test_classification_rule_is_frozen(self) -> None:
        rule = _make_rule("T", "rsi:period=14", "below", threshold=30)
        with pytest.raises(AttributeError):
            rule.token = "NEW"  # type: ignore[misc]


# ── Below / Above conditions ──────────────────────────────────────


class TestTokenizeThreshold:
    def test_below_triggered(self) -> None:
        rules = [_make_rule("RSI_BLW_30", "rsi:period=14", "below", threshold=30)]
        features = {"rsi:period=14": 25.0}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "RSI_BLW_30" in result.tokens

    def test_below_not_triggered(self) -> None:
        rules = [_make_rule("RSI_BLW_30", "rsi:period=14", "below", threshold=30)]
        features = {"rsi:period=14": 45.0}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "RSI_BLW_30" not in result.tokens

    def test_below_at_threshold_not_triggered(self) -> None:
        """Exactly at threshold — strict less-than, should NOT trigger."""
        rules = [_make_rule("RSI_BLW_30", "rsi:period=14", "below", threshold=30)]
        features = {"rsi:period=14": 30.0}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "RSI_BLW_30" not in result.tokens

    def test_above_triggered(self) -> None:
        rules = [_make_rule("RSI_ABV_70", "rsi:period=14", "above", threshold=70)]
        features = {"rsi:period=14": 75.0}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "RSI_ABV_70" in result.tokens

    def test_above_not_triggered(self) -> None:
        rules = [_make_rule("RSI_ABV_70", "rsi:period=14", "above", threshold=70)]
        features = {"rsi:period=14": 55.0}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "RSI_ABV_70" not in result.tokens

    def test_above_at_threshold_not_triggered(self) -> None:
        """Exactly at threshold — strict greater-than, should NOT trigger."""
        rules = [_make_rule("RSI_ABV_70", "rsi:period=14", "above", threshold=70)]
        features = {"rsi:period=14": 70.0}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "RSI_ABV_70" not in result.tokens

    def test_multiple_threshold_rules(self) -> None:
        rules = [
            _make_rule("RSI_BLW_30", "rsi:period=14", "below", threshold=30),
            _make_rule("RSI_BLW_20", "rsi:period=14", "below", threshold=20),
        ]
        features = {"rsi:period=14": 15.0}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "RSI_BLW_30" in result.tokens
        assert "RSI_BLW_20" in result.tokens


# ── Reference conditions (BB band comparisons) ────────────────────


class TestTokenizeReference:
    def test_above_ref_triggered(self) -> None:
        """Close above BB upper band."""
        rules = [_make_rule(
            "BB_ABV_UPR", "_close", "above_ref",
            reference_key="bb:period=20,std=2.0:upper",
        )]
        features = {"bb:period=20,std=2.0:upper": 1.1050}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1100)
        assert "BB_ABV_UPR" in result.tokens

    def test_above_ref_not_triggered(self) -> None:
        rules = [_make_rule(
            "BB_ABV_UPR", "_close", "above_ref",
            reference_key="bb:period=20,std=2.0:upper",
        )]
        features = {"bb:period=20,std=2.0:upper": 1.1050}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "BB_ABV_UPR" not in result.tokens

    def test_below_ref_triggered(self) -> None:
        """Close below BB lower band."""
        rules = [_make_rule(
            "BB_BLW_LWR", "_close", "below_ref",
            reference_key="bb:period=20,std=2.0:lower",
        )]
        features = {"bb:period=20,std=2.0:lower": 1.0900}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.0850)
        assert "BB_BLW_LWR" in result.tokens

    def test_below_ref_not_triggered(self) -> None:
        rules = [_make_rule(
            "BB_BLW_LWR", "_close", "below_ref",
            reference_key="bb:period=20,std=2.0:lower",
        )]
        features = {"bb:period=20,std=2.0:lower": 1.0900}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.0950)
        assert "BB_BLW_LWR" not in result.tokens


# ── Crossover with reference (MACD line vs signal) ────────────────


class TestTokenizeCrossover:
    def test_cross_above_triggered(self) -> None:
        """MACD line crosses above signal line."""
        rules = [_make_rule(
            "MACD_XABV_SIG",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_above",
            reference_key="macd:fast=12,slow=26,signal=9:signal",
        )]
        features = {
            "macd:fast=12,slow=26,signal=9:line": 0.5,
            "macd:fast=12,slow=26,signal=9:signal": 0.3,
        }
        previous = {
            "macd:fast=12,slow=26,signal=9:line": 0.2,
            "macd:fast=12,slow=26,signal=9:signal": 0.3,
        }
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XABV_SIG" in result.tokens

    def test_cross_above_not_triggered_already_above(self) -> None:
        """Was already above signal — no crossover."""
        rules = [_make_rule(
            "MACD_XABV_SIG",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_above",
            reference_key="macd:fast=12,slow=26,signal=9:signal",
        )]
        features = {
            "macd:fast=12,slow=26,signal=9:line": 0.5,
            "macd:fast=12,slow=26,signal=9:signal": 0.3,
        }
        previous = {
            "macd:fast=12,slow=26,signal=9:line": 0.4,
            "macd:fast=12,slow=26,signal=9:signal": 0.3,
        }
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XABV_SIG" not in result.tokens

    def test_cross_below_triggered(self) -> None:
        rules = [_make_rule(
            "MACD_XBLW_SIG",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_below",
            reference_key="macd:fast=12,slow=26,signal=9:signal",
        )]
        features = {
            "macd:fast=12,slow=26,signal=9:line": 0.2,
            "macd:fast=12,slow=26,signal=9:signal": 0.3,
        }
        previous = {
            "macd:fast=12,slow=26,signal=9:line": 0.4,
            "macd:fast=12,slow=26,signal=9:signal": 0.3,
        }
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XBLW_SIG" in result.tokens

    def test_cross_skipped_no_previous(self) -> None:
        """Crossover rules are skipped when no previous features provided."""
        rules = [_make_rule(
            "MACD_XABV_SIG",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_above",
            reference_key="macd:fast=12,slow=26,signal=9:signal",
        )]
        features = {
            "macd:fast=12,slow=26,signal=9:line": 0.5,
            "macd:fast=12,slow=26,signal=9:signal": 0.3,
        }
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "MACD_XABV_SIG" not in result.tokens


# ── Crossover with threshold value ────────────────────────────────


class TestTokenizeCrossoverVal:
    def test_cross_above_val_triggered(self) -> None:
        """MACD line crosses above zero."""
        rules = [_make_rule(
            "MACD_XABV_0",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_above_val",
            threshold=0,
        )]
        features = {"macd:fast=12,slow=26,signal=9:line": 0.1}
        previous = {"macd:fast=12,slow=26,signal=9:line": -0.05}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XABV_0" in result.tokens

    def test_cross_above_val_not_triggered(self) -> None:
        rules = [_make_rule(
            "MACD_XABV_0",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_above_val",
            threshold=0,
        )]
        features = {"macd:fast=12,slow=26,signal=9:line": 0.1}
        previous = {"macd:fast=12,slow=26,signal=9:line": 0.05}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XABV_0" not in result.tokens

    def test_cross_below_val_triggered(self) -> None:
        rules = [_make_rule(
            "MACD_XBLW_0",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_below_val",
            threshold=0,
        )]
        features = {"macd:fast=12,slow=26,signal=9:line": -0.1}
        previous = {"macd:fast=12,slow=26,signal=9:line": 0.05}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XBLW_0" in result.tokens

    def test_cross_val_skipped_no_previous(self) -> None:
        rules = [_make_rule(
            "MACD_XABV_0",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_above_val",
            threshold=0,
        )]
        features = {"macd:fast=12,slow=26,signal=9:line": 0.1}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "MACD_XABV_0" not in result.tokens


# ── Rising / Falling (OBV direction) ──────────────────────────────


class TestTokenizeRisingFalling:
    def test_rising_triggered(self) -> None:
        rules = [_make_rule("OBV_RISING", "obv:", "rising")]
        features = {"obv:": 150000.0}
        previous = {"obv:": 140000.0}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "OBV_RISING" in result.tokens

    def test_rising_not_triggered_falling(self) -> None:
        rules = [_make_rule("OBV_RISING", "obv:", "rising")]
        features = {"obv:": 130000.0}
        previous = {"obv:": 140000.0}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "OBV_RISING" not in result.tokens

    def test_rising_not_triggered_equal(self) -> None:
        """Strict greater-than — equal values should NOT trigger rising."""
        rules = [_make_rule("OBV_RISING", "obv:", "rising")]
        features = {"obv:": 140000.0}
        previous = {"obv:": 140000.0}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "OBV_RISING" not in result.tokens

    def test_falling_triggered(self) -> None:
        rules = [_make_rule("OBV_FALLING", "obv:", "falling")]
        features = {"obv:": 130000.0}
        previous = {"obv:": 140000.0}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "OBV_FALLING" in result.tokens

    def test_rising_falling_skipped_no_previous(self) -> None:
        rules = [
            _make_rule("OBV_RISING", "obv:", "rising"),
            _make_rule("OBV_FALLING", "obv:", "falling"),
        ]
        features = {"obv:": 150000.0}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "OBV_RISING" not in result.tokens
        assert "OBV_FALLING" not in result.tokens


# ── Edge cases ────────────────────────────────────────────────────


class TestTokenizeEdgeCases:
    def test_missing_feature_skips_rule(self) -> None:
        """If the feature key is missing from the dict, the rule is skipped."""
        rules = [_make_rule("RSI_BLW_30", "rsi:period=14", "below", threshold=30)]
        features: dict[str, float] = {}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "RSI_BLW_30" not in result.tokens

    def test_missing_reference_feature_skips_rule(self) -> None:
        rules = [_make_rule(
            "BB_ABV_UPR", "_close", "above_ref",
            reference_key="bb:period=20,std=2.0:upper",
        )]
        features: dict[str, float] = {}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert "BB_ABV_UPR" not in result.tokens

    def test_empty_rules_returns_empty_tokens(self) -> None:
        features = {"rsi:period=14": 50.0}
        result = tokenize("EUR_USD", BASE_TIME, features, [], close=1.1000)
        assert len(result.tokens) == 0

    def test_token_set_instrument_and_time(self) -> None:
        rules = [_make_rule("RSI_BLW_30", "rsi:period=14", "below", threshold=30)]
        features = {"rsi:period=14": 25.0}
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        assert result.instrument == "EUR_USD"
        assert result.time == BASE_TIME

    def test_token_set_is_frozen(self) -> None:
        result = TokenSet(instrument="EUR_USD", time=BASE_TIME, tokens=frozenset())
        with pytest.raises(AttributeError):
            result.instrument = "BTC_USD"  # type: ignore[misc]

    def test_token_set_tokens_is_frozenset(self) -> None:
        result = TokenSet(
            instrument="EUR_USD", time=BASE_TIME, tokens=frozenset({"A", "B"}),
        )
        assert isinstance(result.tokens, frozenset)

    def test_missing_previous_feature_key_skips_crossover(self) -> None:
        """Previous features exist but missing the specific key — skip rule."""
        rules = [_make_rule(
            "MACD_XABV_0",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_above_val",
            threshold=0,
        )]
        features = {"macd:fast=12,slow=26,signal=9:line": 0.1}
        previous: dict[str, float] = {}  # key missing from previous
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XABV_0" not in result.tokens

    def test_cross_above_missing_reference_in_values(self) -> None:
        """cross_above rule skipped when reference_key missing from current values."""
        rules = [_make_rule(
            "MACD_XABV_SIG",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_above",
            reference_key="macd:fast=12,slow=26,signal=9:signal",
        )]
        features = {"macd:fast=12,slow=26,signal=9:line": 0.5}  # no signal key
        previous = {
            "macd:fast=12,slow=26,signal=9:line": 0.2,
            "macd:fast=12,slow=26,signal=9:signal": 0.3,
        }
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XABV_SIG" not in result.tokens

    def test_cross_above_missing_key_in_previous(self) -> None:
        """cross_above skipped when feature_key missing from previous."""
        rules = [_make_rule(
            "MACD_XABV_SIG",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_above",
            reference_key="macd:fast=12,slow=26,signal=9:signal",
        )]
        features = {
            "macd:fast=12,slow=26,signal=9:line": 0.5,
            "macd:fast=12,slow=26,signal=9:signal": 0.3,
        }
        previous: dict[str, float] = {}  # keys missing from previous
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XABV_SIG" not in result.tokens

    def test_cross_below_missing_reference_in_values(self) -> None:
        """cross_below rule skipped when reference_key missing from current values."""
        rules = [_make_rule(
            "MACD_XBLW_SIG",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_below",
            reference_key="macd:fast=12,slow=26,signal=9:signal",
        )]
        features = {"macd:fast=12,slow=26,signal=9:line": 0.2}
        previous = {
            "macd:fast=12,slow=26,signal=9:line": 0.4,
            "macd:fast=12,slow=26,signal=9:signal": 0.3,
        }
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XBLW_SIG" not in result.tokens

    def test_cross_below_missing_key_in_previous(self) -> None:
        """cross_below skipped when keys missing from previous."""
        rules = [_make_rule(
            "MACD_XBLW_SIG",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_below",
            reference_key="macd:fast=12,slow=26,signal=9:signal",
        )]
        features = {
            "macd:fast=12,slow=26,signal=9:line": 0.2,
            "macd:fast=12,slow=26,signal=9:signal": 0.3,
        }
        previous: dict[str, float] = {}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XBLW_SIG" not in result.tokens

    def test_cross_below_val_missing_previous_key(self) -> None:
        """cross_below_val skipped when feature_key missing from previous."""
        rules = [_make_rule(
            "MACD_XBLW_0",
            "macd:fast=12,slow=26,signal=9:line",
            "cross_below_val",
            threshold=0,
        )]
        features = {"macd:fast=12,slow=26,signal=9:line": -0.1}
        previous: dict[str, float] = {}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MACD_XBLW_0" not in result.tokens

    def test_rising_missing_previous_key(self) -> None:
        """rising skipped when feature_key missing from previous dict."""
        rules = [_make_rule("OBV_RISING", "obv:", "rising")]
        features = {"obv:": 150000.0}
        previous: dict[str, float] = {}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "OBV_RISING" not in result.tokens

    def test_falling_missing_previous_key(self) -> None:
        """falling skipped when feature_key missing from previous dict."""
        rules = [_make_rule("OBV_FALLING", "obv:", "falling")]
        features = {"obv:": 130000.0}
        previous: dict[str, float] = {}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "OBV_FALLING" not in result.tokens

    def test_unknown_condition_returns_no_token(self) -> None:
        """Unknown condition type is silently skipped."""
        rules = [_make_rule("MYSTERY", "rsi:period=14", "invalid_condition", threshold=50)]
        features = {"rsi:period=14": 25.0}
        previous = {"rsi:period=14": 25.0}
        result = tokenize(
            "EUR_USD", BASE_TIME, features, rules,
            close=1.1000, previous_features=previous,
        )
        assert "MYSTERY" not in result.tokens


# ── Integration with real classification configs ──────────────────


class TestRealClassifications:
    def test_load_eur_usd_classifications(self) -> None:
        rules = load_classifications(
            "config/classifications/EUR_USD_classifications.json"
        )
        assert len(rules) == 22
        tokens = {r.token for r in rules}
        assert "EURUSD_RSI14_CL_BLW_30" in tokens
        assert "EURUSD_MACD12269_CL_XABV_SIG" in tokens
        assert "EURUSD_BB2020_CL_ABV_UPR" in tokens
        assert "EURUSD_OBV_CL_RISING" in tokens
        assert "EURUSD_ATR14_PIP_ABV_80" in tokens

    def test_load_btc_usd_classifications(self) -> None:
        rules = load_classifications(
            "config/classifications/BTC_USD_classifications.json"
        )
        assert len(rules) == 22
        tokens = {r.token for r in rules}
        assert "BTCUSD_RSI14_CL_BLW_30" in tokens
        assert "BTCUSD_MACD12269_CL_XABV_SIG" in tokens
        assert "BTCUSD_BB2020_CL_ABV_UPR" in tokens
        assert "BTCUSD_OBV_CL_RISING" in tokens
        assert "BTCUSD_ATR14_USD_ABV_1000" in tokens

    def test_eur_usd_tokenize_rsi_oversold(self) -> None:
        """Integration: load real EUR/USD rules, tokenize with oversold RSI."""
        rules = load_classifications(
            "config/classifications/EUR_USD_classifications.json"
        )
        features = {
            "rsi:period=14": 18.0,
            "macd:fast=12,slow=26,signal=9:line": 0.001,
            "macd:fast=12,slow=26,signal=9:signal": 0.002,
            "macd:fast=12,slow=26,signal=9:histogram": -0.001,
            "bb:period=20,std=2.0:upper": 1.1050,
            "bb:period=20,std=2.0:lower": 1.0950,
            "obv:": 100000.0,
            "atr:period=14": 0.005,
        }
        result = tokenize("EUR_USD", BASE_TIME, features, rules, close=1.1000)
        # RSI at 18 — triggers both BLW_20 and BLW_30
        assert "EURUSD_RSI14_CL_BLW_20" in result.tokens
        assert "EURUSD_RSI14_CL_BLW_30" in result.tokens
        # RSI not above 70/80
        assert "EURUSD_RSI14_CL_ABV_70" not in result.tokens
        assert "EURUSD_RSI14_CL_ABV_80" not in result.tokens
        # MACD line > 0
        assert "EURUSD_MACD12269_CL_ABV_0" in result.tokens
        # MACD histogram < 0
        assert "EURUSD_MACD12269_HIST_BLW_0" in result.tokens
        # Close between BB bands — neither ABV_UPR nor BLW_LWR
        assert "EURUSD_BB2020_CL_ABV_UPR" not in result.tokens
        assert "EURUSD_BB2020_CL_BLW_LWR" not in result.tokens
