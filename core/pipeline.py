from __future__ import annotations

from typing import Any

from core.context import DecisionContext
from indicators.pipeline import add_all_indicators
from strategy.candidate import score_latest
from strategy.entry import EntryTimingEngine
from strategy.exit import ExitDecisionEngine, PositionState
from strategy.learning import LearningEngine
from strategy.portfolio import Holding, PortfolioManagerEngine, PortfolioState
from strategy.position_sizing import AccountState, PositionSizingInput, PositionSizingEngine
from strategy.risk import RiskEngine, RiskInput


class ADEPipeline:
    """Integrated ADE v1.0 decision pipeline.

    Execution order:
    1. Indicator enrichment
    2. Candidate decision
    3. Risk decision
    4. Position sizing, capped by Risk Engine
    5. Entry timing
    6. Exit decision when current_position exists
    7. Portfolio decision when holdings exist
    8. Learning decision when learning_samples exist
    """

    def __init__(self) -> None:
        self.risk_engine = RiskEngine()
        self.position_engine = PositionSizingEngine()
        self.entry_engine = EntryTimingEngine()
        self.exit_engine = ExitDecisionEngine()
        self.portfolio_engine = PortfolioManagerEngine()
        self.learning_engine = LearningEngine()

    def run(self, context: DecisionContext) -> DecisionContext:
        enriched = add_all_indicators(context.market_data)
        context.market_data = enriched

        latest = score_latest(enriched)
        context.add_decision("candidate", latest)

        risk = self.risk_engine.evaluate(
            RiskInput(
                account_balance=context.account_balance,
                equity_peak=context.equity_peak or context.account_balance,
                daily_pnl=context.daily_pnl,
                portfolio_heat=context.portfolio_heat,
                cash_weight=context.cash / context.account_balance,
                vix=context.vix,
                market_regime=context.market_regime,
            )
        )
        context.add_decision("risk", risk)

        sizing = self.position_engine.recommend(
            PositionSizingInput(
                ticker=context.ticker,
                price=float(latest["close"]),
                grade=str(latest["grade"]),
                confidence=float(latest["confidence"]),
                risk_level=str(latest["risk_level"]),
                atr=self._latest_atr(enriched),
                market_regime=context.market_regime,
                account=AccountState(
                    account_balance=context.account_balance,
                    cash=context.cash,
                ),
            )
        )
        sizing = self._apply_risk_cap(sizing.to_dict(), risk.to_dict(), context)
        context.add_decision("position", sizing)

        entry = self.entry_engine.evaluate(
            enriched,
            candidate=latest,
            position=sizing,
            market_regime=context.market_regime,
        )
        context.add_decision("entry", entry)

        if context.current_position:
            try:
                exit_decision = self.exit_engine.evaluate(
                    enriched,
                    position=PositionState(
                        ticker=context.ticker,
                        entry_price=float(context.current_position["entry_price"]),
                        shares=int(context.current_position["shares"]),
                        current_price=float(latest["close"]),
                        highest_price=context.current_position.get("highest_price"),
                        holding_days=int(context.current_position.get("holding_days", 0)),
                        stop_loss_price=context.current_position.get("stop_loss_price"),
                    ),
                    candidate=latest,
                )
                context.add_decision("exit", exit_decision)
            except Exception as exc:  # defensive integration boundary
                context.add_error(f"exit: {exc}")

        if context.holdings:
            try:
                portfolio = self.portfolio_engine.evaluate(
                    PortfolioState(
                        account_balance=context.account_balance,
                        cash=context.cash,
                        market_regime=context.market_regime,
                        holdings=[Holding(**holding) for holding in context.holdings],
                    )
                )
                context.add_decision("portfolio", portfolio)
            except Exception as exc:  # defensive integration boundary
                context.add_error(f"portfolio: {exc}")

        if context.learning_samples:
            try:
                learning = self.learning_engine.evaluate(context.learning_samples)
                context.add_decision("learning", learning)
            except Exception as exc:  # defensive integration boundary
                context.add_error(f"learning: {exc}")

        return context

    def _latest_atr(self, enriched) -> float | None:
        for column in ["ATR", "ATR14", "atr", "atr14"]:
            if column in enriched.columns:
                value = enriched.iloc[-1][column]
                if value == value:
                    return float(value)
        return None

    def _apply_risk_cap(
        self,
        sizing: dict[str, Any],
        risk: dict[str, Any],
        context: DecisionContext,
    ) -> dict[str, Any]:
        cap = float(risk.get("max_new_position_weight", sizing.get("recommended_weight", 0.0)))
        current_weight = float(sizing.get("recommended_weight", 0.0))
        if current_weight <= cap:
            return sizing

        price = float(sizing.get("buy_amount", 0.0)) / max(int(sizing.get("shares", 0)), 1)
        capped_amount = context.account_balance * cap
        capped_shares = int(capped_amount // price) if price > 0 else 0
        sizing = dict(sizing)
        sizing["recommended_weight"] = round(cap, 4)
        sizing["buy_amount"] = round(capped_shares * price, 2)
        sizing["shares"] = capped_shares
        sizing["risk_capped"] = True
        sizing.setdefault("reasons", [])
        sizing["reasons"].append("Position size capped by Risk Engine")
        return sizing


def run_pipeline(context: DecisionContext) -> DecisionContext:
    return ADEPipeline().run(context)
