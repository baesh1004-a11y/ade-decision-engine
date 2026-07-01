from __future__ import annotations

from typing import Any

from core.context import DecisionContext
from indicators.pipeline import add_all_indicators
from pattern.context import PatternContextEngine
from strategy.candidate import score_latest
from strategy.entry import EntryTimingEngine
from strategy.exit import ExitDecisionEngine, PositionState
from strategy.learning import LearningEngine
from strategy.portfolio import Holding, PortfolioManagerEngine, PortfolioState
from strategy.position_sizing import AccountState, PositionSizingInput, PositionSizingEngine
from strategy.risk import RiskEngine, RiskInput


class ADEPipeline:
    """Integrated ADE v1.0 decision pipeline."""

    def __init__(self) -> None:
        self.pattern_context_engine = PatternContextEngine(window=20, top_k=10, horizons=(5, 10, 20, 40))
        self.risk_engine = RiskEngine()
        self.position_engine = PositionSizingEngine()
        self.entry_engine = EntryTimingEngine()
        self.exit_engine = ExitDecisionEngine()
        self.portfolio_engine = PortfolioManagerEngine()
        self.learning_engine = LearningEngine()

    def run(self, context: DecisionContext) -> DecisionContext:
        enriched = add_all_indicators(context.market_data)
        context.market_data = enriched

        pattern_context = self._evaluate_pattern_context(enriched, context)
        if pattern_context:
            context.add_decision("pattern_context", pattern_context)
            context.add_decision("pattern", pattern_context.get("pattern", {}))

        latest = score_latest(enriched)
        if pattern_context:
            latest = self._apply_pattern_context_to_candidate(latest, pattern_context)
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
            except Exception as exc:
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
            except Exception as exc:
                context.add_error(f"portfolio: {exc}")

        if context.learning_samples:
            try:
                learning = self.learning_engine.evaluate(context.learning_samples)
                context.add_decision("learning", learning)
            except Exception as exc:
                context.add_error(f"learning: {exc}")

        return context

    def _evaluate_pattern_context(self, enriched, context: DecisionContext) -> dict[str, Any] | None:
        try:
            return self.pattern_context_engine.evaluate(
                enriched,
                ticker=context.ticker,
                market_regime=context.market_regime,
                vix=context.vix,
            ).to_dict()
        except ValueError as exc:
            context.add_error(f"pattern_context: {exc}")
            return None

    def _apply_pattern_context_to_candidate(self, candidate: dict[str, Any], pattern_context: dict[str, Any]) -> dict[str, Any]:
        adjusted = dict(candidate)
        score = int(adjusted.get("score", 0))
        confidence = float(adjusted.get("confidence", 0.0))
        reasons = list(adjusted.get("reasons", []))
        flags = list(adjusted.get("risk_flags", []))

        expected_20d = float(pattern_context.get("expected_returns", {}).get("return_20d", 0.0))
        win_rate_20d = float(pattern_context.get("win_rates", {}).get("win_rate_20d", 0.0))
        combined_similarity = float(pattern_context.get("combined_similarity", 0.0))
        context_similarity = float(pattern_context.get("context_similarity", 0.0))
        pattern_flags = list(pattern_context.get("risk_flags", []))

        adjustment = 0
        confidence_delta = 0.0
        if combined_similarity >= 0.80 and context_similarity >= 0.70 and expected_20d >= 0.03 and win_rate_20d >= 0.60:
            adjustment = 12
            confidence_delta = 0.06
            reasons.append("Pattern Context: similar chart and market context show strong 20-day evidence")
        elif combined_similarity >= 0.72 and expected_20d > 0 and win_rate_20d >= 0.50:
            adjustment = 6
            confidence_delta = 0.03
            reasons.append("Pattern Context: chart and context provide supportive evidence")
        elif expected_20d < 0 or "Context-adjusted negative 20-day expected return" in pattern_flags:
            adjustment = -12
            confidence_delta = -0.06
            flags.append("Pattern Context negative forward evidence")
            reasons.append("Pattern Context: similar chart-context cases show weak forward return")
        elif "Low combined pattern-context similarity" in pattern_flags or "Low context similarity" in pattern_flags:
            adjustment = -6
            confidence_delta = -0.03
            flags.append("Pattern Context weak similarity")
            reasons.append("Pattern Context: historical context evidence is weak")

        adjusted["score"] = max(0, min(100, score + adjustment))
        adjusted["confidence"] = round(max(0.0, min(1.0, confidence + confidence_delta)), 4)
        adjusted["grade"] = self._grade(adjusted["score"])
        adjusted["action"] = self._candidate_action(adjusted["score"], adjusted.get("risk_level", "LOW"))
        adjusted["risk_flags"] = flags
        adjusted["reasons"] = reasons
        adjusted["pattern_context_adjustment"] = {
            "score_delta": adjustment,
            "confidence_delta": round(confidence_delta, 4),
            "expected_20d": round(expected_20d, 4),
            "win_rate_20d": round(win_rate_20d, 4),
            "combined_similarity": round(combined_similarity, 4),
            "context_similarity": round(context_similarity, 4),
        }
        return adjusted

    def _grade(self, score: int) -> str:
        if score >= 85:
            return "A"
        if score >= 70:
            return "B"
        if score >= 55:
            return "C"
        if score >= 40:
            return "D"
        return "F"

    def _candidate_action(self, score: int, risk_level: str) -> str:
        if risk_level == "HIGH":
            return "WATCH"
        if score >= 85:
            return "BUY_CANDIDATE"
        if score >= 70:
            return "WATCHLIST"
        if score >= 55:
            return "NEUTRAL"
        return "REJECT"

    def _latest_atr(self, enriched) -> float | None:
        for column in ["ATR", "ATR14", "atr", "atr14"]:
            if column in enriched.columns:
                value = enriched.iloc[-1][column]
                if value == value:
                    return float(value)
        return None

    def _apply_risk_cap(self, sizing: dict[str, Any], risk: dict[str, Any], context: DecisionContext) -> dict[str, Any]:
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
