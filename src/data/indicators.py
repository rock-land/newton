"""Technical Indicator Provider v1 (RSI, MACD, Bollinger Bands, OBV, ATR)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from typing import Any

import numpy as np

from src.data.feature_provider import FeatureMetadata
from src.data.fetcher_base import CandleRecord

_talib: Any | None
try:
    import talib as _talib
except ModuleNotFoundError:  # pragma: no cover - exercised only in environments without TA-Lib
    _talib = None

talib: Any | None = _talib


@dataclass(frozen=True)
class TechnicalIndicatorConfig:
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    atr_period: int = 14


class TechnicalIndicatorProvider:
    def __init__(self, config: TechnicalIndicatorConfig | None = None) -> None:
        self.config = config or TechnicalIndicatorConfig()

    @property
    def provider_name(self) -> str:
        return "technical_indicator_provider_v1"

    @property
    def feature_namespace(self) -> str:
        return "technical"

    def get_features(
        self,
        *,
        instrument: str,
        interval: str,
        candles: list[CandleRecord],
        lookback: int,
    ) -> dict[datetime, dict[str, float]]:
        if lookback <= 0:
            msg = "lookback must be > 0"
            raise ValueError(msg)

        filtered = [c for c in candles if c.instrument == instrument and c.interval == interval]
        ordered = sorted(filtered, key=lambda c: c.time)
        if not ordered:
            return {}

        closes = [c.close for c in ordered]
        highs = [c.high for c in ordered]
        lows = [c.low for c in ordered]
        volumes = [c.volume for c in ordered]

        rsi = _compute_rsi(closes, self.config.rsi_period)
        macd_line, macd_signal, macd_hist = _compute_macd(
            closes,
            fast=self.config.macd_fast,
            slow=self.config.macd_slow,
            signal=self.config.macd_signal,
        )
        bb_upper, bb_middle, bb_lower = _compute_bollinger_bands(
            closes,
            period=self.config.bb_period,
            std_mult=self.config.bb_std,
        )
        obv = _compute_obv(closes, volumes)
        atr = _compute_atr(highs, lows, closes, period=self.config.atr_period)

        out: dict[datetime, dict[str, float]] = {}
        for idx, candle in enumerate(ordered):
            features: dict[str, float] = {}

            if rsi[idx] is not None:
                rsi_value = rsi[idx]
                if rsi_value is None:
                    msg = "rsi value is unexpectedly None"
                    raise ValueError(msg)
                features[f"rsi:period={self.config.rsi_period}"] = rsi_value

            if macd_line[idx] is not None and macd_signal[idx] is not None and macd_hist[idx] is not None:
                prefix = (
                    f"macd:fast={self.config.macd_fast},"
                    f"slow={self.config.macd_slow},signal={self.config.macd_signal}"
                )
                line_value = macd_line[idx]
                signal_value = macd_signal[idx]
                hist_value = macd_hist[idx]
                if line_value is None or signal_value is None or hist_value is None:
                    msg = "macd values are unexpectedly None"
                    raise ValueError(msg)
                features[f"{prefix}:line"] = line_value
                features[f"{prefix}:signal"] = signal_value
                features[f"{prefix}:histogram"] = hist_value

            if bb_upper[idx] is not None and bb_middle[idx] is not None and bb_lower[idx] is not None:
                prefix = f"bb:period={self.config.bb_period},std={self.config.bb_std}"
                upper_value = bb_upper[idx]
                middle_value = bb_middle[idx]
                lower_value = bb_lower[idx]
                if upper_value is None or middle_value is None or lower_value is None:
                    msg = "bollinger band values are unexpectedly None"
                    raise ValueError(msg)
                features[f"{prefix}:upper"] = upper_value
                features[f"{prefix}:middle"] = middle_value
                features[f"{prefix}:lower"] = lower_value

            features["obv:"] = obv[idx]

            if atr[idx] is not None:
                atr_value = atr[idx]
                if atr_value is None:
                    msg = "atr value is unexpectedly None"
                    raise ValueError(msg)
                features[f"atr:period={self.config.atr_period}"] = atr_value

            if features:
                out[candle.time] = features

        if len(out) <= lookback:
            return out

        times = sorted(out.keys())[-lookback:]
        return {ts: out[ts] for ts in times}

    def get_feature_metadata(self) -> list[FeatureMetadata]:
        cfg = self.config
        macd_prefix = f"macd:fast={cfg.macd_fast},slow={cfg.macd_slow},signal={cfg.macd_signal}"
        bb_prefix = f"bb:period={cfg.bb_period},std={cfg.bb_std}"
        return [
            FeatureMetadata(
                namespace=self.feature_namespace,
                feature_key=f"rsi:period={cfg.rsi_period}",
                display_name="RSI",
                description="Relative Strength Index",
                unit=None,
                params={"period": cfg.rsi_period},
                provider=self.provider_name,
            ),
            FeatureMetadata(
                namespace=self.feature_namespace,
                feature_key=f"{macd_prefix}:line",
                display_name="MACD Line",
                description="Moving Average Convergence Divergence line",
                unit=None,
                params={"fast": cfg.macd_fast, "slow": cfg.macd_slow, "signal": cfg.macd_signal, "component": "line"},
                provider=self.provider_name,
            ),
            FeatureMetadata(
                namespace=self.feature_namespace,
                feature_key=f"{macd_prefix}:signal",
                display_name="MACD Signal",
                description="MACD signal line",
                unit=None,
                params={"fast": cfg.macd_fast, "slow": cfg.macd_slow, "signal": cfg.macd_signal, "component": "signal"},
                provider=self.provider_name,
            ),
            FeatureMetadata(
                namespace=self.feature_namespace,
                feature_key=f"{macd_prefix}:histogram",
                display_name="MACD Histogram",
                description="MACD line minus signal line",
                unit=None,
                params={"fast": cfg.macd_fast, "slow": cfg.macd_slow, "signal": cfg.macd_signal, "component": "histogram"},
                provider=self.provider_name,
            ),
            FeatureMetadata(
                namespace=self.feature_namespace,
                feature_key=f"{bb_prefix}:upper",
                display_name="Bollinger Upper",
                description="Bollinger Bands upper band",
                unit=None,
                params={"period": cfg.bb_period, "std": cfg.bb_std, "component": "upper"},
                provider=self.provider_name,
            ),
            FeatureMetadata(
                namespace=self.feature_namespace,
                feature_key=f"{bb_prefix}:middle",
                display_name="Bollinger Middle",
                description="Bollinger Bands middle band",
                unit=None,
                params={"period": cfg.bb_period, "std": cfg.bb_std, "component": "middle"},
                provider=self.provider_name,
            ),
            FeatureMetadata(
                namespace=self.feature_namespace,
                feature_key=f"{bb_prefix}:lower",
                display_name="Bollinger Lower",
                description="Bollinger Bands lower band",
                unit=None,
                params={"period": cfg.bb_period, "std": cfg.bb_std, "component": "lower"},
                provider=self.provider_name,
            ),
            FeatureMetadata(
                namespace=self.feature_namespace,
                feature_key="obv:",
                display_name="OBV",
                description="On-Balance Volume",
                unit=None,
                params={},
                provider=self.provider_name,
            ),
            FeatureMetadata(
                namespace=self.feature_namespace,
                feature_key=f"atr:period={cfg.atr_period}",
                display_name="ATR",
                description="Average True Range",
                unit=None,
                params={"period": cfg.atr_period},
                provider=self.provider_name,
            ),
        ]


def _to_optional_float_list(values: np.ndarray) -> list[float | None]:
    return [None if np.isnan(value) else float(value) for value in values]


def _compute_rsi(closes: list[float], period: int) -> list[float | None]:
    if talib is not None:
        return _to_optional_float_list(talib.RSI(np.asarray(closes, dtype=float), timeperiod=period))

    # Compatibility fallback for environments where TA-Lib wheels/native libs are unavailable.
    return _manual_compute_rsi(closes, period)


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _compute_ema(values: list[float], span: int) -> list[float]:
    alpha = 2.0 / (span + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append((alpha * value) + ((1 - alpha) * out[-1]))
    return out


def _compute_macd(
    closes: list[float],
    *,
    fast: int,
    slow: int,
    signal: int,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    if talib is not None:
        macd, macd_signal, macd_hist = talib.MACD(
            np.asarray(closes, dtype=float),
            fastperiod=fast,
            slowperiod=slow,
            signalperiod=signal,
        )
        return (
            _to_optional_float_list(macd),
            _to_optional_float_list(macd_signal),
            _to_optional_float_list(macd_hist),
        )

    # Compatibility fallback for environments where TA-Lib wheels/native libs are unavailable.
    return _manual_compute_macd(closes, fast=fast, slow=slow, signal=signal)


def _compute_bollinger_bands(
    closes: list[float],
    *,
    period: int,
    std_mult: float,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    if talib is not None:
        upper, middle, lower = talib.BBANDS(
            np.asarray(closes, dtype=float),
            timeperiod=period,
            nbdevup=std_mult,
            nbdevdn=std_mult,
            matype=talib.MA_Type.SMA,
        )
        return (
            _to_optional_float_list(upper),
            _to_optional_float_list(middle),
            _to_optional_float_list(lower),
        )

    # Compatibility fallback for environments where TA-Lib wheels/native libs are unavailable.
    return _manual_compute_bollinger_bands(closes, period=period, std_mult=std_mult)


def _compute_obv(closes: list[float], volumes: list[float]) -> list[float]:
    if talib is not None:
        return [float(value) for value in talib.OBV(np.asarray(closes, dtype=float), np.asarray(volumes, dtype=float))]

    # Compatibility fallback for environments where TA-Lib wheels/native libs are unavailable.
    return _manual_compute_obv(closes, volumes)


def _compute_atr(highs: list[float], lows: list[float], closes: list[float], *, period: int) -> list[float | None]:
    if talib is not None:
        return _to_optional_float_list(
            talib.ATR(
                np.asarray(highs, dtype=float),
                np.asarray(lows, dtype=float),
                np.asarray(closes, dtype=float),
                timeperiod=period,
            )
        )

    # Compatibility fallback for environments where TA-Lib wheels/native libs are unavailable.
    return _manual_compute_atr(highs, lows, closes, period=period)


def _manual_compute_rsi(closes: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    out[period] = _rsi_from_avgs(avg_gain, avg_loss)

    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        out[i] = _rsi_from_avgs(avg_gain, avg_loss)

    return out


def _manual_compute_macd(
    closes: list[float],
    *,
    fast: int,
    slow: int,
    signal: int,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    n = len(closes)
    line: list[float | None] = [None] * n
    sig: list[float | None] = [None] * n
    hist: list[float | None] = [None] * n
    if n < slow + signal:
        return line, sig, hist

    ema_fast = _compute_ema(closes, fast)
    ema_slow = _compute_ema(closes, slow)
    raw_macd = [f - s for f, s in zip(ema_fast, ema_slow)]

    first_line = slow - 1
    line_series = raw_macd[first_line:]
    signal_series = _compute_ema(line_series, signal)

    for offset, value in enumerate(line_series):
        idx = first_line + offset
        line[idx] = value

    first_signal = first_line + signal - 1
    for offset, value in enumerate(signal_series[signal - 1 :]):
        idx = first_signal + offset
        sig[idx] = value
        line_value = line[idx]
        if line_value is None:
            continue
        hist[idx] = line_value - value

    return line, sig, hist


def _manual_compute_bollinger_bands(
    closes: list[float],
    *,
    period: int,
    std_mult: float,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    n = len(closes)
    upper: list[float | None] = [None] * n
    middle: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    if n < period:
        return upper, middle, lower

    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / period
        variance = sum((v - mean) ** 2 for v in window) / period
        std_dev = sqrt(variance)
        middle[i] = mean
        upper[i] = mean + (std_mult * std_dev)
        lower[i] = mean - (std_mult * std_dev)

    return upper, middle, lower


def _manual_compute_obv(closes: list[float], volumes: list[float]) -> list[float]:
    out = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out.append(out[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            out.append(out[-1] - volumes[i])
        else:
            out.append(out[-1])
    return out


def _manual_compute_atr(highs: list[float], lows: list[float], closes: list[float], *, period: int) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < period:
        return out

    tr: list[float] = []
    for i in range(n):
        if i == 0:
            tr.append(highs[i] - lows[i])
            continue
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))

    atr = sum(tr[:period]) / period
    out[period - 1] = atr

    for i in range(period, n):
        atr = ((atr * (period - 1)) + tr[i]) / period
        out[i] = atr

    return out
