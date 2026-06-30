from pykrx import stock
import pandas as pd

class KoreaCollector:
    """Collect OHLCV data from KRX using PyKRX."""

    def get_daily(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        df = stock.get_market_ohlcv(start, end, ticker)
        df = df.reset_index()
        df = df.rename(columns={
            '날짜':'Date',
            '시가':'Open',
            '고가':'High',
            '저가':'Low',
            '종가':'Close',
            '거래량':'Volume'
        })
        return df
