"""
Bonus: accuracy assessment across ammeter types - descriptive only, with an
honest limitation.

The three emulators do NOT measure a shared physical quantity. Each call
draws fresh random inputs inside the device (Greenlee: V and R; ENTES: B and
K; CIRCUTOR: a burst of voltages and a time step) and returns only the
computed current. There is no way to feed a known reference current, so
cross-device ACCURACY cannot be measured through this API: differences in
outputs reflect the different random input models, not device error, and
output spread reflects the randomized inputs, not device repeatability. No
"most accurate device" ranking is therefore produced.

What is implemented instead is deliberately descriptive, not inferential:
each device's empirical mean is placed next to the theoretical expected mean
of its documented model, with the deviation in percent and the sample count
stated. No confidence interval and no pass/fail claim: the distributions are
skewed, a normal-approximation interval would be unreliable at small n, and
the empirical mean is itself a random quantity whose agreement with the
model is expected only in probability as the sample count grows.
"""
from typing import Dict

# Theoretical expectations under the documented random-input models.
# Greenlee: I = V/R, V~U[1,10], R~U[0.1,100]  ->  E[I] = E[V]*E[1/R]
#   E[1/R] = ln(100/0.1)/(100-0.1) = ln(1000)/99.9 ~ 0.06915 -> E[I] ~ 0.3803A
# ENTES: I = B*K, B~U[0.01,0.1], K~U[500,2000] -> E[I] = 0.055*1250 = 68.75A
# CIRCUTOR: I = sum of 10 samples V_i*dt, V_i~U[0.1,1.0], dt~U[0.001,0.01]
#   -> E[I] = 10 * 0.55 * 0.0055 = 0.03025A
DOCUMENTED_MODELS = {
    "greenlee": {"expected_mean": 5.5 * 0.06915, "model": "I = V/R, V~U[1,10], R~U[0.1,100]"},
    "entes": {"expected_mean": 68.75, "model": "I = B*K, B~U[0.01,0.1], K~U[500,2000]"},
    "circutor": {"expected_mean": 0.03025, "model": "I = sum(V_i*dt), 10 samples, V~U[0.1,1.0], dt~U[0.001,0.01]"},
}

LIMITATION = (
    "No shared reference current exists: each ammeter generates its own random "
    "inputs per call, so cross-device accuracy cannot be determined from this "
    "API, and output spread reflects the randomized inputs rather than device "
    "repeatability. No device is ranked as 'most accurate'. The comparison "
    "below is descriptive only and makes no inferential claim: the empirical "
    "mean is itself random and agreement with the documented model is "
    "expected only in probability as the sample count grows."
)


def assess_conformance(ammeter_type: str, statistics_dict: Dict[str, float]) -> dict:
    model = DOCUMENTED_MODELS.get(ammeter_type)
    if model is None:
        # A device added via config only has no documented model: report that
        # instead of crashing the whole run.
        return {
            "ammeter_type": ammeter_type,
            "status": "no_documented_model",
            "reason": "no documented model for this ammeter type "
                      "(add one to DOCUMENTED_MODELS to enable the comparison)",
            "sample_count": statistics_dict["count"],
            "limitation": LIMITATION,
        }
    n = statistics_dict["count"]
    if n < 2:
        return {
            "ammeter_type": ammeter_type,
            "status": "insufficient_data",
            "reason": "fewer than two successful measurements",
            "sample_count": n,
            "limitation": LIMITATION,
        }
    empirical_mean = statistics_dict["mean"]
    expected = model["expected_mean"]
    deviation_pct = abs(empirical_mean - expected) / expected * 100 if expected else None
    return {
        "ammeter_type": ammeter_type,
        "status": "descriptive_comparison",
        "documented_model": model["model"],
        "theoretical_expected_mean": round(expected, 6),
        "empirical_mean": round(empirical_mean, 6),
        "deviation_pct": round(deviation_pct, 2),
        "sample_count": n,
        "limitation": LIMITATION,
    }
