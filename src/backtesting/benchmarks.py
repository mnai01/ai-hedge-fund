from __future__ import annotations

from datetime import datetime
import pandas as pd
from dateutil.relativedelta import relativedelta

from src.tools.api import get_price_data


class BenchmarkCalculator:
    def get_return_pct(self, ticker: str, start_date: str, end_date: str) -> float | None:
        """Compute simple buy-and-hold return % for ticker from start_date to end_date.

        Return is (last_close / first_close - 1) * 100, or None if unavailable.
        """
        try:
            # Handle single-day case by extending the date range
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            
            if start_dt >= end_dt:
                # Single day or invalid range - extend end by 1 day
                end_dt = end_dt + relativedelta(days=1)
                end_date = end_dt.strftime("%Y-%m-%d")
            
            df = get_price_data(ticker, start_date, end_date)
            if df.empty:
                return None
            first_close = df.iloc[0]["close"]
            last_close = df.iloc[-1]["close"]
            if first_close is None or pd.isna(first_close):
                return None
            if last_close is None or pd.isna(last_close):
                # Try last valid close
                last_valid = df["close"].dropna()
                if last_valid.empty:
                    return None
                last_close = float(last_valid.iloc[-1])
            return (float(last_close) / float(first_close) - 1.0) * 100.0
        except Exception:
            return None


