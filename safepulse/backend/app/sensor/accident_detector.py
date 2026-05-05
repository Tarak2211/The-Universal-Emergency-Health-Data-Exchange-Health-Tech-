import math
from dataclasses import dataclass
from datetime import datetime, timedelta

GRAVITY = 9.81
HIGH_IMPACT_THRESHOLD = 4.0   # G — potential crash
SEVERE_THRESHOLD = 8.0        # G — severe crash
STILLNESS_WINDOW_SEC = 3.0    # seconds to observe post-impact
STILLNESS_THRESHOLD = 1.2     # G — if avg post-impact > this, it's a drop not a crash

@dataclass
class SensorReading:
    ax: float  # m/s²
    ay: float
    az: float
    timestamp: datetime

def calculate_g_force(ax: float, ay: float, az: float) -> float:
    return math.sqrt(ax**2 + ay**2 + az**2) / GRAVITY

def is_accident(readings: list[SensorReading]) -> dict:
    """
    Two-phase detection:
    Phase 1: Detect high-impact spike (crash event)
    Phase 2: Confirm post-impact stillness (victim incapacitated)

    False alarm filter: A dropped phone spikes then shows movement
    as someone picks it up. A crash victim stays still.
    """
    impact_reading = None
    for r in readings:
        g = calculate_g_force(r.ax, r.ay, r.az)
        if g >= HIGH_IMPACT_THRESHOLD:
            impact_reading = r
            break

    if not impact_reading:
        return {"accident": False, "reason": "no_impact_detected"}

    window_end = impact_reading.timestamp + timedelta(seconds=STILLNESS_WINDOW_SEC)
    post_impact = [r for r in readings if impact_reading.timestamp < r.timestamp <= window_end]

    if not post_impact:
        return {"accident": False, "reason": "insufficient_post_impact_data"}

    avg_g_post = sum(calculate_g_force(r.ax, r.ay, r.az) for r in post_impact) / len(post_impact)

    if avg_g_post > STILLNESS_THRESHOLD:
        return {"accident": False, "reason": "false_alarm_phone_drop"}

    peak_g = calculate_g_force(impact_reading.ax, impact_reading.ay, impact_reading.az)
    return {
        "accident": True,
        "severity": "severe" if peak_g >= SEVERE_THRESHOLD else "moderate",
        "peak_g_force": round(peak_g, 2),
        "timestamp": impact_reading.timestamp.isoformat()
    }
