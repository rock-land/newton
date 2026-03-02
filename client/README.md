# Newton Client

Stage-1 thin client health panel for Newton.

## Run

```bash
cd /home/bj/.openclaw/workspace/projects/newton/client
npm start
```

Open: <http://localhost:4173>

The panel polls `/api/v1/health` and shows:
- API health + request latency
- DB status
- Broker connectivity (Oanda/Binance)
- Per-instrument last candle age (`EUR_USD`, `BTC_USD`)
