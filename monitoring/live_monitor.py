from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from broker.kis import kis_broker_from_env
from datahub.repository import PriceRepository


@dataclass(frozen=True)
class LiveQuote:
    market: str
    ticker: str
    name: str | None
    source: str
    price: float
    previous_close: float
    change: float
    change_rate: float
    open: float
    high: float
    low: float
    volume: float
    trade_amount: float
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LiveMonitorRow:
    kind: str
    market: str
    ticker: str
    name: str | None
    price: float
    change_rate: float
    reference_price: float | None
    pnl_rate: float | None
    seven_day_up_probability: float | None
    seven_day_expected_return: float | None
    prediction_grade: str | None
    status: str
    reason: str
    source: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class KISIntradayQuoteSource:
    """Domestic stock quote polling source using KIS REST current-price API."""

    def __init__(self) -> None:
        self.broker = kis_broker_from_env()

    def quote(self, market: str, ticker: str, name: str | None = None) -> LiveQuote:
        if market.lower() != "kr":
            raise ValueError("KIS intraday quote source currently supports Korean stocks only")
        payload = self.broker._get(  # guarded by the broker's token/rate-limit/retry implementation
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id="FHKST01010100",
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        )
        row = payload.get("output") or {}
        price = self._num(row.get("stck_prpr"))
        previous_close = self._num(row.get("stck_sdpr"))
        change = self._num(row.get("prdy_vrss"))
        change_rate = self._num(row.get("prdy_ctrt"))
        return LiveQuote(
            market=market.lower(),
            ticker=ticker,
            name=name,
            source="KIS",
            price=price,
            previous_close=previous_close,
            change=change,
            change_rate=change_rate,
            open=self._num(row.get("stck_oprc")),
            high=self._num(row.get("stck_hgpr")),
            low=self._num(row.get("stck_lwpr")),
            volume=self._num(row.get("acml_vol")),
            trade_amount=self._num(row.get("acml_tr_pbmn")),
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )

    @staticmethod
    def _num(value: object) -> float:
        try:
            return float(str(value).replace(",", ""))
        except Exception:
            return 0.0


class LocalCloseQuoteSource:
    """Fallback source when KIS credentials or quote calls are unavailable."""

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.repo = PriceRepository(db_path)

    def close(self) -> None:
        self.repo.close()

    def quote(self, market: str, ticker: str, name: str | None = None) -> LiveQuote:
        df = self.repo.fetch_dataframe(market, ticker, source="fdr")
        if df.empty:
            df = self.repo.fetch_dataframe(market, ticker)
        if df.empty:
            raise ValueError(f"No local price data: {market}:{ticker}")
        close = pd.to_numeric(df["Close"], errors="coerce").dropna()
        if close.empty:
            raise ValueError(f"No local close data: {market}:{ticker}")
        price = float(close.iloc[-1])
        previous = float(close.iloc[-2]) if len(close) > 1 else price
        change = price - previous
        rate = 0.0 if previous <= 0 else change / previous * 100.0
        return LiveQuote(
            market=market.lower(), ticker=ticker, name=name, source="LOCAL_CLOSE",
            price=price, previous_close=previous, change=change, change_rate=rate,
            open=price, high=price, low=price, volume=0.0, trade_amount=0.0,
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )


class ADELiveMonitor:
    def __init__(self, db_path: str | Path = "datahub/market.db", prefer_kis: bool = True) -> None:
        self.db_path = Path(db_path)
        self.prefer_kis = prefer_kis
        self.local = LocalCloseQuoteSource(self.db_path)
        self.kis: KISIntradayQuoteSource | None = None
        self.kis_error: str | None = None
        if prefer_kis:
            try:
                self.kis = KISIntradayQuoteSource()
            except Exception as exc:
                self.kis_error = str(exc)

    def close(self) -> None:
        self.local.close()

    def monitor(
        self,
        recommendations: Iterable[object],
        positions: pd.DataFrame,
    ) -> list[LiveMonitorRow]:
        targets: dict[str, dict[str, object]] = {}
        for item in recommendations:
            market = str(getattr(item, "market", "kr")).lower()
            ticker = str(getattr(item, "ticker", ""))
            if not ticker:
                continue
            prediction = getattr(item, "prediction", None)
            targets[f"R:{market}:{ticker}"] = {
                "kind": "RECOMMENDATION", "market": market, "ticker": ticker,
                "name": getattr(item, "name", None), "reference_price": None,
                "prediction": prediction,
            }
        if not positions.empty:
            for _, row in positions.iterrows():
                market = str(row.get("market", "kr")).lower()
                ticker = str(row.get("ticker", ""))
                if not ticker:
                    continue
                targets[f"P:{market}:{ticker}"] = {
                    "kind": "POSITION", "market": market, "ticker": ticker,
                    "name": row.get("name"),
                    "reference_price": float(row.get("avg_reference_price", 0) or 0),
                    "prediction": None,
                }

        rows: list[LiveMonitorRow] = []
        for target in targets.values():
            quote = self._quote(str(target["market"]), str(target["ticker"]), target.get("name"))
            reference = target.get("reference_price")
            pnl_rate = None
            if reference is not None and float(reference) > 0:
                pnl_rate = (quote.price / float(reference) - 1.0) * 100.0
            prediction = target.get("prediction")
            seven_up = getattr(prediction, "seven_day_up_probability", None) if prediction is not None else None
            seven_ret = getattr(prediction, "seven_day_expected_return", None) if prediction is not None else None
            grade = getattr(prediction, "grade", None) if prediction is not None else None
            status, reason = self._status(str(target["kind"]), quote.change_rate, pnl_rate, seven_up, seven_ret)
            rows.append(
                LiveMonitorRow(
                    kind=str(target["kind"]), market=quote.market, ticker=quote.ticker,
                    name=quote.name, price=quote.price, change_rate=quote.change_rate,
                    reference_price=float(reference) if reference is not None else None,
                    pnl_rate=pnl_rate,
                    seven_day_up_probability=float(seven_up) if seven_up is not None else None,
                    seven_day_expected_return=float(seven_ret) if seven_ret is not None else None,
                    prediction_grade=str(grade) if grade is not None else None,
                    status=status, reason=reason, source=quote.source, updated_at=quote.updated_at,
                )
            )
        return sorted(rows, key=lambda x: (x.status == "ALERT", x.kind == "POSITION", abs(x.change_rate)), reverse=True)

    def _quote(self, market: str, ticker: str, name: str | None) -> LiveQuote:
        if self.kis is not None:
            try:
                return self.kis.quote(market, ticker, name)
            except Exception as exc:
                self.kis_error = str(exc)
        return self.local.quote(market, ticker, name)

    @staticmethod
    def _status(
        kind: str,
        change_rate: float,
        pnl_rate: float | None,
        seven_up: float | None,
        seven_ret: float | None,
    ) -> tuple[str, str]:
        if kind == "POSITION":
            if pnl_rate is not None and pnl_rate <= -7:
                return "ALERT", f"보유수익률 {pnl_rate:.2f}%로 손절 검토 구간"
            if change_rate <= -4:
                return "ALERT", f"장중 등락률 {change_rate:.2f}%로 급락"
            if pnl_rate is not None and pnl_rate >= 7:
                return "WATCH", f"보유수익률 {pnl_rate:.2f}%로 이익실현 검토"
            return "NORMAL", "보유 상태 정상 범위"
        if change_rate >= 4:
            return "WATCH", f"추천 후 장중 {change_rate:+.2f}% 상승해 추격매수 주의"
        if change_rate <= -3:
            return "ALERT", f"장중 {change_rate:+.2f}% 하락해 매수 보류 검토"
        if seven_up is not None and seven_ret is not None and seven_up >= 70 and seven_ret > 0:
            return "BUY ZONE", f"7일 상승확률 {seven_up:.1f}%, 기대수익 {seven_ret:+.2f}%"
        return "WATCH", "실시간 가격과 Replay 예측을 함께 확인"
