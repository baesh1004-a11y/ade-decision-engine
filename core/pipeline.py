from __future__ import annotations

from typing import Any

from calibration.persistence import CalibrationRepository
from calibration.updater import ProbabilityUpdater
from core.context import DecisionContext
from explain.engine import ExplainableAIEngine
from indicators.pipeline import add_all_indicators
from pattern.context import PatternContextEngine
from pattern.memory import PatternMemoryBuilder, PatternMemoryRepository
from pattern.memory_matching import PatternMemoryMatchingEngine
from strategy.candidate import score_latest
from strategy.entry import EntryTimingEngine
from strategy.exit import ExitDecisionEngine, PositionState
from strategy.learning import LearningEngine
from strategy.portfolio import Holding, PortfolioManagerEngine, PortfolioState
from strategy.position_sizing import AccountState, PositionSizingInput, PositionSizingEngine
from strategy.probability import ProbabilityEngine
from strategy.risk import RiskEngine, RiskInput


class ADEPipeline:
    """Integrated ADE pipeline with memory, calibration, and explainability."""

    def __init__(
        self,
        memory_repository: PatternMemoryRepository | None = None,
        calibration_repository: CalibrationRepository | None = None,
        use_calibration: bool = True,
        use_explainability: bool = True,
        auto_build_memory: bool = True,
        memory_window: int = 20,
        memory_top_k: int = 10,
        horizons: tuple[int, ...] = (5, 10, 20, 40),
    ) -> None:
        self.memory_repository = memory_repository or PatternMemoryRepository()
        self.calibration_repository = calibration_repository
        self.use_calibration = use_calibration
        self.use_explainability = use_explainability
        self.auto_build_memory = auto_build_memory
        self.memory_window = memory_window
        self.memory_top_k = memory_top_k
        self.horizons = horizons
        self.memory_builder = PatternMemoryBuilder(window=memory_window, horizons=horizons)
        self.memory_matching_engine = PatternMemoryMatchingEngine(
            self.memory_repository,
            window=memory_window,
            top_k=memory_top_k,
            horizons=horizons,
        )
        self.pattern_context_engine = PatternContextEngine(window=memory_window, top_k=memory_top_k, horizons=horizons)
        self.probability_engine = ProbabilityEngine(horizon_days=20)
        self.probability_updater = ProbabilityUpdater()
        self.explain_engine = ExplainableAIEngine()
        self.risk_engine = RiskEngine()
        self.position_engine = PositionSizingEngine()
        self.entry_engine = EntryTimingEngine()
        self.exit_engine = ExitDecisionEngine()
        self.portfolio_engine = PortfolioManagerEngine()
        self.learning_engine = LearningEngine()

    def run(self, context: DecisionContext) -> DecisionContext:
        enriched = add_all_indicators(context.market_data)
        context.market_data = enriched

        pattern_context = self._evaluate_memory_pattern_context(enriched, context)
        probability: dict[str, Any] | None = None
        if pattern_context:
            context.add_decision("pattern_context", pattern_context)
            context.add_decision("pattern", pattern_context.get("pattern", {}))
            context.add_decision(
                "pattern_memory",
                {
                    "records": self.memory_repository.count(
                        market=context.market,
                        ticker=context.ticker,
                        window=self.memory_window,
                    ),
                    "backend": "sqlite",
                },
            )
            probability = self.probability_engine.evaluate(pattern_context).to_dict()
            probability = self._apply_calibration(probability, context)
            context.add_decision("probability", probability)

        latest = score_latest(enriched)
        if probability:
            latest = self._apply_probability_to_candidate(latest, probability)
        elif pattern_context:
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
                account=AccountState(account_balance=context.account_balance, cash=context.cash),
            )
        )
        sizing = self._apply_risk_cap(sizing.to_dict(), risk.to_dict(), context)
        context.add_decision("position", sizing)

        entry = self.entry_engine.evaluate(enriched, candidate=latest, position=sizing, market_regime=context.market_regime)
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

        if self.use_explainability:
            self._add_explanation(context)

        return context

    def _evaluate_memory_pattern_context(self, enriched, context: DecisionContext) -> dict[str, Any] | None:
        try:
            scoped_count = self.memory_repository.count(
                market=context.market,
                ticker=context.ticker,
                window=self.memory_window,
            )
            if self.auto_build_memory and scoped_count == 0:
                records = self.memory_builder.build_records(enriched, market=context.market, ticker=context.ticker)
                self.memory_repository.bulk_upsert(records)
            memory_match = self.memory_matching_engine.evaluate(enriched, market=context.market, ticker=context.ticker).to_dict()
            return self.pattern_context_engine.evaluate_from_pattern(
                df=enriched,
                pattern=memory_match,
                ticker=context.ticker,
                market_regime=context.market_regime,
                vix=context.vix,
            ).to_dict()
        except ValueError as exc:
            context.add_error(f"pattern_memory: {exc}")
            return None

    def _apply_calibration(self, probability: dict[str, Any], context: DecisionContext) -> dict[str, Any]:
        if not self.use_calibration or self.calibration_repository is None:
            probability = dict(probability)
            probability["calibration"] = {"applied": False, "reason": "Calibration repository not configured"}
            return probability
        try:
            table = self.calibration_repository.fetch_latest_calibration_table(probability.get("horizon", "20d"))
            if table is None:
                probability = dict(probability)
                probability["calibration"] = {"applied": False, "reason": "No calibration table available"}
                return probability
            return self.probability_updater.apply(probability, table)
        except Exception as exc:
            context.add_error(f"calibration: {exc}")
            probability = dict(probability)
            probability["calibration"] = {"applied": False, "reason": str(exc)}
            return probability

    def _add_explanation(self, context: DecisionContext) -> None:
        try:
            explanation = self.explain_engine.explain(context.ticker, context.decisions).to_dict()
            context.add_decision("explanation", explanation)
        except Exception as exc:
            context.add_error(f"explanation: {exc}")

    def _apply_probability_to_candidate(self, candidate: dict[str, Any], probability: dict[str, Any]) -> dict[str, Any]:
        adjusted = dict(candidate)
        score = int(adjusted.get("score", 0))
        confidence = float(adjusted.get("confidence", 0.0))
        reasons = list(adjusted.get("reasons", []))
        flags = list(adjusted.get("risk_flags", []))

        upside = float(probability.get("upside_probability", 0.0))
        expected_return = float(probability.get("expected_return", 0.0))
        risk_reward = float(probability.get("risk_reward", 0.0))
        prob_confidence = float(probability.get("confidence", 0.0))
        recommendation = str(probability.get("recommendation", "WATCH"))
        calibration = probability.get("calibration", {})

        adjustment = 0
        confidence_delta = 0.0
        if recommendation == "STRONG_BUY":
            adjustment = 15
            confidence_delta = 0.08
            reasons.append("Probability Engine: strong upside probability and risk-reward")
        elif recommendation == "BUY":
            adjustment = 8
            confidence_delta = 0.04
            reasons.append("Probability Engine: supportive upside probability")
        elif recommendation == "WATCH":
            adjustment = 3
            confidence_delta = 0.01
            reasons.append("Probability Engine: positive but not decisive probability")
        else:
            adjustment = -15
            confidence_delta = -0.08
            flags.append("Probability Engine avoid signal")
            reasons.append("Probability Engine: probability evidence is unfavorable")

        if calibration.get("applied"):
            reasons.append("Probability Calibration: calibrated probability applied before candidate scoring")

        adjusted["score"] = max(0, min(100, score + adjustment))
        adjusted["confidence"] = round(max(0.0, min(1.0, confidence + confidence_delta)), 4)
        adjusted["grade"] = self._grade(adjusted["score"])
        adjusted["action"] = self._candidate_action(adjusted["score"], adjusted.get("risk_level", "LOW"))
        adjusted["risk_flags"] = flags
        adjusted["reasons"] = reasons
        adjusted["probability_adjustment"] = {
            "score_delta": adjustment,
            "confidence_delta": round(confidence_delta, 4),
            "upside_probability": round(upside, 4),
            "raw_upside_probability": probability.get("raw_upside_probability"),
            "expected_return": round(expected_return, 4),
            "risk_reward": round(risk_reward, 4),
            "probability_confidence": round(prob_confidence, 4),
            "recommendation": recommendation,
            "calibration_applied": bool(calibration.get("applied", False)),
        }
        return adjusted

    def _apply_pattern_context_to_candidate(self, candidate: dict[str, Any], pattern_context: dict[str, Any]) -> dict[str, Any]:
        adjusted = dict(candidate)
        adjusted["pattern_context_adjustment"] = {"score_delta": 0, "note": "Pattern Context available but Probability Engine not available"}
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
