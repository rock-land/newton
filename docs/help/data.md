# Data Viewer

The Data page provides candlestick charting and indicator visualization for OHLCV market data.

## Controls

- **Instrument** — Select EUR_USD or BTC_USD
- **Interval** — Choose the candle timeframe (1m, 5m, 1h, 4h, 1d)
- **Start Date** — Beginning of the date range to fetch
- **Limit** — Maximum number of candles to display

Click "Fetch" to load data from the database.

## Candlestick Chart

The main chart displays OHLCV data as candlesticks:

- **Green candles** — Close above open (bullish)
- **Red candles** — Close below open (bearish)
- **Wicks** — Show the high/low range for each period

## Volume

The volume chart below the price chart shows trading volume for each period, colored to match the candle direction.

## Indicator Overlays

Toggle technical indicators on/off:

- **Bollinger Bands (BB)** — Upper and lower bands overlaid on the price chart, showing volatility envelope
- **RSI** — Relative Strength Index in a separate panel, with overbought (70) and oversold (30) reference lines
- **MACD** — Moving Average Convergence Divergence with signal line and histogram in a separate panel

Indicators are fetched from the features API and require computed features in the database for the selected instrument and interval.

## Summary

The summary card shows candle count, date range, and price range for the loaded data.
