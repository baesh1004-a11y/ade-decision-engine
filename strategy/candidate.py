import pandas as pd


def score_latest(df: pd.DataFrame) -> dict:
    """Score the latest row using the first ADE v0.1 rule set.

    This is not a final trading model. It is a transparent starting score that
    reflects the user's preferred factors: STO, volume, moving average position,
    and candle structure.
    """
    row = df.iloc[-1]
    score = 0
    reasons: list[str] = []

    if row.get("VOL20_RATIO", 0) >= 2:
        score += 20
        reasons.append("Volume is above 2x 20-day average")
    if row.get("VOL20_RATIO", 0) >= 10:
        score += 20
        reasons.append("Volume is above 10x 20-day average")

    if row.get("IS_BULLISH", False) and row.get("BODY_RATIO", 0) >= 0.5:
        score += 15
        reasons.append("Strong bullish candle body")

    if row.get("STO533_K", 100) < 30 and row.get("STO533_K", 0) > row.get("STO533_D", 0):
        score += 15
        reasons.append("STO 5-3-3 early rebound signal")

    if row.get("STO1066_K", 100) < 40:
        score += 10
        reasons.append("STO 10-6-6 is in low zone")

    if row.get("STO201212_K", 100) < 50:
        score += 10
        reasons.append("STO 20-12-12 is not overheated")

    close = row.get("Close")
    ma120 = row.get("MA120")
    if pd.notna(close) and pd.notna(ma120) and close >= ma120:
        score += 10
        reasons.append("Close is above MA120")

    return {
        "score": min(score, 100),
        "reasons": reasons,
        "close": float(row.get("Close", 0)),
    }
