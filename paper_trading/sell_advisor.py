from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository


@dataclass(frozen=True)
class SellAdvice:
    market: str
    ticker: str
    name: str | None
    quantity: int
    current_price: float
    pnl_rate: float
    score: int
    decision: str
    reasons: tuple[str, ...]
    replay_event_id: str | None
    replay_progress_pct: float | None
    replay_week: int | None
    replay_total_weeks: int | None
    target_return: float | None
    replay_mdd: float | None


class PaperSellAdvisor:
    """Generate explainable SELL/HOLD judgments for paper positions.

    This engine does not place orders. It only supplies decision material for
    the human-in-the-loop dashboard.
    """

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.price_repo = PriceRepository(self.db_path)

    def close(self) -> None:
        self.price_repo.close()
        self.conn.close()

    def evaluate_positions(self, positions: pd.DataFrame) -> list[SellAdvice]:
        results: list[SellAdvice] = []
        if positions.empty:
            return results
        for _, row in positions.iterrows():
            results.append(self._evaluate(row))
        return sorted(results, key=lambda x: (x.decision == "SELL", x.score), reverse=True)

    def _evaluate(self, row: pd.Series) -> SellAdvice:
        market = str(row.get("market", "kr")).lower()
        ticker = str(row.get("ticker", ""))
        name = row.get("name")
        quantity = int(float(row.get("quantity", 0) or 0))
        current_price = float(row.get("current_price", 0) or 0)
        pnl_rate = float(row.get("pnl_rate", 0) or 0)
        event_id = str(row.get("top1_event_id") or "") or None
        first_buy_at = str(row.get("first_buy_at") or "")

        score = 0
        reasons: list[str] = []

        replay = self._replay_stats(event_id)
        total_weeks = replay["total_weeks"] if replay else None
        target_return = replay["max_return"] if replay else None
        replay_mdd = replay["max_drawdown"] if replay else None
        held_days = self._holding_days(first_buy_at)
        replay_week = max(1, held_days // 7 + 1) if held_days is not None else None
        progress = None
        if replay_week is not None and total_weeks and total_weeks > 0:
            progress = min(100.0, replay_week / total_weeks * 100)

        if pnl_rate <= -10:
            score += 55
            reasons.append(f"손실률 {pnl_rate:.1f}%로 강한 손절 검토 구간입니다.")
        elif pnl_rate <= -7:
            score += 40
            reasons.append(f"손실률 {pnl_rate:.1f}%로 기본 손절선(-7%)을 하회했습니다.")
        elif pnl_rate <= -4:
            score += 18
            reasons.append(f"손실률 {pnl_rate:.1f}%로 위험구간에 접근하고 있습니다.")

        if target_return is not None and target_return > 0:
            attainment = pnl_rate / target_return * 100
            if attainment >= 100:
                score += 35
                reasons.append(f"현재 수익률이 Replay 최대수익 {target_return:.1f}%를 달성했습니다.")
            elif attainment >= 80:
                score += 24
                reasons.append(f"Replay 목표수익의 {attainment:.0f}%를 달성해 이익실현 검토 구간입니다.")

        if progress is not None:
            if progress >= 100:
                score += 35
                reasons.append(f"Replay 예상기간 {total_weeks}주를 모두 경과했습니다.")
            elif progress >= 85:
                score += 20
                reasons.append(f"Replay 진행률이 {progress:.0f}%로 종료구간에 진입했습니다.")

        trend = self._trend_state(market, ticker)
        if trend["below_ma20"]:
            score += 18
            reasons.append("현재가가 20일 이동평균선 아래로 내려가 추세 약화가 확인됩니다.")
        if trend["return_5d"] <= -5:
            score += 15
            reasons.append(f"최근 5거래일 수익률이 {trend['return_5d']:.1f}%로 단기 하락이 강합니다.")
        elif trend["return_5d"] < 0:
            score += 6
            reasons.append(f"최근 5거래일 수익률이 {trend['return_5d']:.1f}%로 약세입니다.")

        if replay_mdd is not None and replay_mdd < 0 and pnl_rate <= replay_mdd * 0.85:
            score += 22
            reasons.append(f"현재 손실이 Replay MDD {replay_mdd:.1f}%에 근접하거나 초과했습니다.")

        score = min(score, 100)
        decision = "SELL" if score >= 60 else "WATCH" if score >= 35 else "HOLD"
        if not reasons:
            reasons.append("손절·목표수익·Replay 종료·추세 약화 조건이 아직 충족되지 않았습니다.")

        return SellAdvice(
            market=market,
            ticker=ticker,
            name=name if pd.notna(name) else None,
            quantity=quantity,
            current_price=current_price,
            pnl_rate=pnl_rate,
            score=score,
            decision=decision,
            reasons=tuple(reasons),
            replay_event_id=event_id,
            replay_progress_pct=progress,
            replay_week=replay_week,
            replay_total_weeks=total_weeks,
            target_return=target_return,
            replay_mdd=replay_mdd,
        )

    def _replay_stats(self, event_id: str | None) -> dict[str, float | int | None] | None:
        if not event_id:
            return None
        row = self.conn.execute(
            """
            SELECT e.max_return, e.max_drawdown,
                   CAST((COALESCE(MAX(f.day_index), 0) + 6) / 7 AS INTEGER) AS total_weeks
            FROM replay_events e
            LEFT JOIN replay_event_flow f ON f.event_id=e.event_id
            WHERE e.event_id=?
            GROUP BY e.event_id
            """,
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "max_return": float(row["max_return"]) if row["max_return"] is not None else None,
            "max_drawdown": float(row["max_drawdown"]) if row["max_drawdown"] is not None else None,
            "total_weeks": int(row["total_weeks"]) if row["total_weeks"] is not None else None,
        }

    def _trend_state(self, market: str, ticker: str) -> dict[str, float | bool]:
        df = self.price_repo.fetch_dataframe(market, ticker, source="fdr")
        if df.empty:
            df = self.price_repo.fetch_dataframe(market, ticker)
        if df.empty or len(df) < 5:
            return {"below_ma20": False, "return_5d": 0.0}
        close = pd.to_numeric(df["Close"], errors="coerce").dropna()
        if close.empty:
            return {"below_ma20": False, "return_5d": 0.0}
        latest = float(close.iloc[-1])
        ma20 = float(close.tail(20).mean())
        base = float(close.iloc[-5]) if len(close) >= 5 else latest
        return_5d = 0.0 if base <= 0 else (latest / base - 1) * 100
        return {"below_ma20": latest < ma20, "return_5d": return_5d}

    @staticmethod
    def _holding_days(value: str) -> int | None:
        if not value:
            return None
        try:
            return max(0, (datetime.now() - datetime.fromisoformat(value)).days)
        except Exception:
            try:
                return max(0, (datetime.now() - pd.Timestamp(value).to_pydatetime()).days)
            except Exception:
                return None
