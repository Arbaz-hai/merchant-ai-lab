"""A dependency-light public demo for controlled financial-risk AI agents.

All records below are synthetic. The app never connects to payment rails, customer
accounts, or production fraud systems; it makes trust boundaries, policy checks, and
human approvals visible for portfolio review.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
AUDIT_PATH = ROOT / "data" / "audit.jsonl"
MAX_BODY_BYTES = 100_000

FRAUD_TRANSACTIONS = {
    "txn_demo_approved": {
        "amount_inr": 1240,
        "payment_method": "UPI",
        "merchant_category": "grocery",
        "customer_activity": {"account_age_days": 490, "transactions_24h": 2, "failed_auth_24h": 0},
        "device_activity": {"known_device": True, "device_changes_30d": 0},
        "merchant_risk": {"risk_band": "LOW", "chargeback_rate_pct": 0.12},
        "signals": {"blacklisted": False, "velocity": False, "geography": False, "device": False, "amount": False, "behavior": False},
        "features_complete": True,
    },
    "txn_demo_step_up": {
        "amount_inr": 4820,
        "payment_method": "card",
        "merchant_category": "electronics",
        "customer_activity": {"account_age_days": 61, "transactions_24h": 3, "failed_auth_24h": 1},
        "device_activity": {"known_device": True, "device_changes_30d": 1},
        "merchant_risk": {"risk_band": "MEDIUM", "chargeback_rate_pct": 0.54},
        "signals": {"blacklisted": False, "velocity": False, "geography": True, "device": False, "amount": True, "behavior": False},
        "features_complete": True,
    },
    "txn_demo_velocity": {
        "amount_inr": 18800,
        "payment_method": "card",
        "merchant_category": "digital_goods",
        "customer_activity": {"account_age_days": 16, "transactions_24h": 9, "failed_auth_24h": 3},
        "device_activity": {"known_device": False, "device_changes_30d": 3},
        "merchant_risk": {"risk_band": "HIGH", "chargeback_rate_pct": 1.68},
        "signals": {"blacklisted": False, "velocity": True, "geography": True, "device": True, "amount": True, "behavior": True},
        "features_complete": True,
    },
    "txn_demo_blacklist": {
        "amount_inr": 39750,
        "payment_method": "card",
        "merchant_category": "high_value_resale",
        "customer_activity": {"account_age_days": 2, "transactions_24h": 14, "failed_auth_24h": 7},
        "device_activity": {"known_device": False, "device_changes_30d": 5},
        "merchant_risk": {"risk_band": "HIGH", "chargeback_rate_pct": 2.31},
        "signals": {"blacklisted": True, "velocity": True, "geography": True, "device": True, "amount": True, "behavior": True},
        "features_complete": True,
    },
    "txn_demo_incomplete": {
        "amount_inr": 7200,
        "payment_method": "UPI",
        "merchant_category": "unknown",
        "customer_activity": {"account_age_days": None, "transactions_24h": None, "failed_auth_24h": None},
        "device_activity": {"known_device": None, "device_changes_30d": None},
        "merchant_risk": {"risk_band": "UNKNOWN", "chargeback_rate_pct": None},
        "signals": {},
        "features_complete": False,
    },
}

MERCHANT_GROWTH_DATA = {
    "merchant_demo_01": {
        "period": "Last 30 synthetic days",
        "metrics": {
            "revenue_inr": 648000,
            "transaction_count": 4680,
            "average_order_value_inr": 138.5,
            "refund_rate_pct": 0.7,
            "repeat_customer_rate_pct": 31.0,
            "settlement_timing": "T+1; 98.6% on schedule",
            "payment_method_mix_pct": {"upi": 63, "cards": 22, "wallets": 15},
            "revenue_change_pct": 9.4,
            "transaction_change_pct": 7.7,
        },
        "history_complete": True,
    },
    "merchant_demo_02": {
        "period": "Last 30 synthetic days",
        "metrics": {
            "revenue_inr": 324000,
            "transaction_count": 1720,
            "average_order_value_inr": 188.4,
            "refund_rate_pct": 2.1,
            "repeat_customer_rate_pct": 19.0,
            "settlement_timing": "T+1; 95.8% on schedule",
            "payment_method_mix_pct": {"upi": 51, "cards": 37, "wallets": 12},
            "revenue_change_pct": -3.2,
            "transaction_change_pct": -5.1,
        },
        "history_complete": True,
    },
    "merchant_demo_incomplete": {
        "period": "Last 30 synthetic days",
        "metrics": {"revenue_inr": 114000, "transaction_count": None, "average_order_value_inr": None},
        "history_complete": False,
    },
}

PROMPT_INJECTION_RULES = [
    (
        r"\b(ignore|disregard|override|forget)\b.{0,48}\b(previous|prior|all|system)\b.{0,48}\b(instructions?|rules?|polic(?:y|ies)|prompt)\b",
        "instruction override attempt",
        35,
    ),
    (
        r"\b(reveal|show|print|send|exfiltrate)\b.{0,48}\b(password|secret|token|api[ _-]?key|system prompt|system instructions?|credential)\b",
        "secret extraction attempt",
        45,
    ),
    (
        r"\b(do not tell|without (?:the )?user|silently|secretly)\b.{0,60}\b(transfer|refund|payment|approve|delete)\b",
        "covert action request",
        35,
    ),
    (
        r"\b(system message|developer message|tool instruction)\b.{0,80}\b(you must|must now|override|ignore)\b",
        "authority impersonation",
        30,
    ),
    (
        r"\b(pichle|purane|saare)\b.{0,32}\b(nirdesh|instruction)\b.{0,32}\b(ignore|bhool)\b",
        "Hindi instruction override attempt",
        35,
    ),
]

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clamp_text(value: Any, max_chars: int = 30_000) -> str:
    if value is None:
        return ""
    return str(value).strip()[:max_chars]


def analyze_prompt_injection(text: str) -> dict[str, Any]:
    """Score untrusted text using transparent, inspectable detection rules."""
    text = clamp_text(text)
    if not text:
        return {
            "decision": "allow",
            "risk_score": 0,
            "signals": [],
            "recommended_action": "No untrusted text was supplied.",
        }

    normalized = re.sub(r"\s+", " ", text.lower())
    signals: list[str] = []
    score = 0
    for pattern, label, weight in PROMPT_INJECTION_RULES:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            signals.append(label)
            score += weight

    if "```" in text and any(word in normalized for word in ("instruction", "prompt", "system")):
        signals.append("embedded instruction-like code block")
        score += 12
    if len(re.findall(r"(?:https?://|www\.)", normalized)) > 4:
        signals.append("unusually link-dense external content")
        score += 8

    score = min(score, 100)
    if score >= 45:
        decision = "block"
        action = "Quarantine this source. Do not pass it to the agent or execute actions derived from it."
    elif score >= 20:
        decision = "review"
        action = "Keep this source untrusted and require a human review before any action with external effect."
    else:
        decision = "allow"
        action = "Continue with normal source isolation and least-privilege tool access."
    return {
        "decision": decision,
        "risk_score": score,
        "signals": signals,
        "recommended_action": action,
    }


def append_audit(event: dict[str, Any]) -> None:
    """Write a minimal synthetic trace for the demo without storing raw source text."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def _masked_reference(value: str) -> str:
    """Keep a stable audit reference without persisting a raw identifier."""
    return f"{value[:4]}_•••{value[-3:]}" if len(value) > 7 else "redacted"


def _untrusted_input_guard(payload: dict[str, Any]) -> dict[str, Any]:
    """Free text and metadata are always data, never instructions."""
    untrusted_context = clamp_text(
        payload.get("untrusted_context") or payload.get("external_context"), 30_000
    )
    metadata = clamp_text(payload.get("transaction_metadata") or payload.get("merchant_data"), 30_000)
    return analyze_prompt_injection("\n".join(part for part in (untrusted_context, metadata) if part))


def _ml_risk_model(record: dict[str, Any]) -> tuple[int, float]:
    """Run a fixed-weight, reproducible model surrogate on verified synthetic features.

    It intentionally does not train on customer data. Fixed coefficients make this
    portfolio demo inspectable while preserving the ML-model control point.
    """
    signals = record["signals"]
    activity = record["customer_activity"]
    merchant = record["merchant_risk"]
    score = 6
    score += 72 if signals["blacklisted"] else 0
    score += 22 if signals["velocity"] else 0
    score += 12 if signals["geography"] else 0
    score += 12 if signals["device"] else 0
    score += 9 if signals["amount"] else 0
    score += 6 if signals["behavior"] else 0
    score += {"LOW": 0, "MEDIUM": 5, "HIGH": 8}.get(merchant["risk_band"], 0)
    score += 7 if int(activity["failed_auth_24h"]) >= 3 else 0
    score = min(99, score)
    confidence = 0.95 if score >= 60 else 0.91 if score <= 30 else 0.86
    return score, confidence


def _risk_decision(score: int) -> tuple[str, str, bool, bool]:
    if score >= 85:
        return "CRITICAL", "ESCALATE", True, True
    if score >= 60:
        return "HIGH", "HOLD", True, True
    if score >= 30:
        return "MEDIUM", "STEP_UP", False, False
    return "LOW", "ALLOW", False, False


def _fraud_evidence(record: dict[str, Any], model_score: int, quarantined: bool) -> list[str]:
    signals = record["signals"]
    activity = record["customer_activity"]
    merchant = record["merchant_risk"]
    evidence = [
        f"Verified synthetic transaction amount: INR {record['amount_inr']:,}; payment method: {record['payment_method'].upper()}.",
        "Blacklist check: MATCH" if signals["blacklisted"] else "Blacklist check: no match.",
        "Velocity signal: elevated" if signals["velocity"] else "Velocity signal: within approved threshold.",
        "Geography signal: mismatch observed" if signals["geography"] else "Geography signal: consistent with baseline.",
        "Device signal: unfamiliar device" if signals["device"] else "Device signal: recognized or stable.",
        "Amount signal: anomalous" if signals["amount"] else "Amount signal: within expected range.",
        "Behavioral signal: anomalous" if signals["behavior"] else "Behavioral signal: no anomaly observed.",
        f"Merchant risk band: {merchant['risk_band']}; synthetic chargeback baseline: {merchant['chargeback_rate_pct']}%.",
        f"ML risk-model score: {model_score}/100 using verified synthetic features.",
    ]
    if int(activity["failed_auth_24h"]) > 0:
        evidence.append(f"Recent failed-authentication count: {activity['failed_auth_24h']} (synthetic aggregate).")
    if quarantined:
        evidence.append("Untrusted external text was quarantined and did not modify the decision.")
    return evidence


def investigate_fraud(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the strict FraudShield contract using only verified synthetic records."""
    transaction_id = clamp_text(payload.get("transaction_id"), 120)
    if transaction_id not in FRAUD_TRANSACTIONS:
        return {
            "transaction_id": transaction_id or "unknown",
            "risk_score": 65,
            "risk_level": "HIGH",
            "recommended_action": "ESCALATE",
            "evidence": ["INSUFFICIENT_EVIDENCE: no verified synthetic transaction record was available."],
            "reasoning_summary": "INSUFFICIENT_EVIDENCE: the requested record was not found. Escalated without creating or inferring transaction details.",
            "confidence": 0.0,
            "case_created": True,
            "human_approval_required": True,
        }

    record = FRAUD_TRANSACTIONS[transaction_id]
    guard = _untrusted_input_guard(payload)
    quarantined = guard["decision"] in {"block", "review"}
    if not record["features_complete"]:
        result = {
            "transaction_id": transaction_id,
            "risk_score": 65,
            "risk_level": "HIGH",
            "recommended_action": "ESCALATE",
            "evidence": [
                "INSUFFICIENT_EVIDENCE: customer, device, or merchant-risk features are incomplete.",
                "No ML risk score was generated because verified feature data is incomplete.",
            ] + (["Untrusted external text was quarantined and did not modify the decision."] if quarantined else []),
            "reasoning_summary": "INSUFFICIENT_EVIDENCE: policy requires escalation when evidence is incomplete; no permanent block or reversal was attempted.",
            "confidence": 0.0,
            "case_created": True,
            "human_approval_required": True,
        }
    else:
        score, confidence = _ml_risk_model(record)
        level, action, case_created, human_approval = _risk_decision(score)
        result = {
            "transaction_id": transaction_id,
            "risk_score": score,
            "risk_level": level,
            "recommended_action": action,
            "evidence": _fraud_evidence(record, score, quarantined),
            "reasoning_summary": (
                f"Verified synthetic transaction, customer/device aggregate, merchant-risk, and model evidence align to {level} policy. "
                "Any irreversible payment or account action requires an authorized human or policy engine."
            ),
            "confidence": confidence,
            "case_created": case_created,
            "human_approval_required": human_approval,
        }
    append_audit(
        {
            "at": now_iso(),
            "event": "fraud_investigation",
            "transaction_ref": _masked_reference(transaction_id),
            "risk_level": result["risk_level"],
            "recommended_action": result["recommended_action"],
            "case_created": result["case_created"],
        }
    )
    return result


def _growth_recommendations(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if metrics["repeat_customer_rate_pct"] < 35:
        recommendations.append(
            {
                "title": "Draft an opt-in returning-customer reminder",
                "action": "Prepare a consent-based reorder reminder for merchant review; do not publish automatically.",
                "expected_impact": "Potential 2-4 percentage-point repeat-customer lift; not guaranteed.",
                "estimated_cost": "Low: merchant-approved campaign setup and offer funding.",
                "risk": "Medium: validate consent, targeting rules, and offer margin before publication.",
                "confidence": 0.72,
                "requires_approval": True,
            }
        )
    if metrics["refund_rate_pct"] > 1.0:
        recommendations.append(
            {
                "title": "Investigate top refund drivers",
                "action": "Review merchant-provided order and fulfilment aggregates before changing operations.",
                "expected_impact": "Could reduce avoidable refund rate; the effect depends on validated root causes.",
                "estimated_cost": "Low to medium: operational review time.",
                "risk": "Low: do not infer individual customer causes from aggregate data.",
                "confidence": 0.79,
                "requires_approval": True,
            }
        )
    if metrics["revenue_change_pct"] < 0:
        recommendations.append(
            {
                "title": "Test a small merchant-approved payment-method offer",
                "action": "Draft a time-bounded offer for a permitted payment method; publish only after approval.",
                "expected_impact": "May improve conversion on selected payment methods; not a revenue guarantee.",
                "estimated_cost": "Medium: offer funding subject to merchant margin review.",
                "risk": "Medium: cap budget and measure incrementality before scaling.",
                "confidence": 0.63,
                "requires_approval": True,
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "title": "Protect service level while testing one approved retention idea",
                "action": "Create a small opt-in experiment draft and review results before expanding it.",
                "expected_impact": "Potential incremental retention improvement; not guaranteed.",
                "estimated_cost": "Low: limited pilot budget.",
                "risk": "Low: require merchant approval and a defined stop condition.",
                "confidence": 0.61,
                "requires_approval": True,
            }
        )
    return recommendations[:3]


def recommend_merchant_growth(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the strict Merchant Growth contract from permitted business aggregates."""
    merchant_id = clamp_text(payload.get("merchant_id"), 120)
    record = MERCHANT_GROWTH_DATA.get(merchant_id)
    guard = _untrusted_input_guard(payload)
    quarantined = guard["decision"] in {"block", "review"}
    if not record or not record["history_complete"]:
        result = {
            "merchant_id": merchant_id or "unknown",
            "period": record["period"] if record else "unknown",
            "summary": "INSUFFICIENT_EVIDENCE: required verified merchant history is missing or contradictory; escalated for data-quality review.",
            "observed_metrics": record["metrics"] if record else {},
            "recommendations": [],
            "draft_campaigns": [],
            "data_limitations": [
                "Transaction, retention, settlement, or payment-method history is incomplete.",
                "No forecast or campaign recommendation was produced from incomplete data.",
            ] + (["Untrusted external text was quarantined and ignored."] if quarantined else []),
        }
    else:
        metrics = record["metrics"]
        forecast = round(metrics["revenue_inr"] * (1 + metrics["revenue_change_pct"] / 100), 0)
        observed_metrics = dict(metrics)
        observed_metrics["forecast_next_30_days_inr"] = {
            "value": forecast,
            "label": "Forecast, not observed fact",
            "assumption": "Recent aggregate revenue trend remains directionally stable; no guarantee of growth.",
        }
        recommendations = _growth_recommendations(metrics)
        result = {
            "merchant_id": merchant_id,
            "period": record["period"],
            "summary": "Observed aggregate payment metrics are separated from the forecast and action assumptions. Recommendations are drafts only and require merchant approval.",
            "observed_metrics": observed_metrics,
            "recommendations": recommendations,
            "draft_campaigns": [{"title": "Opt-in returning-customer reminder", "status": "DRAFT_ONLY - not published", "approval_required": True}],
            "data_limitations": (["Untrusted external text was quarantined and ignored."] if quarantined else []),
        }
    append_audit(
        {
            "at": now_iso(),
            "event": "merchant_growth_recommendation",
            "merchant_ref": _masked_reference(merchant_id or "unknown"),
            "recommendation_count": len(result["recommendations"]),
            "data_limitations": len(result["data_limitations"]),
        }
    )
    return result


class DigitPredictor:
    """Tiny real MLP service based on sklearn's built-in handwritten-digits dataset.

    A transparent template fallback keeps the rest of the demo usable if the optional
    ML dependency is unavailable, for example during a minimal local checkout.
    """

    _lock = threading.Lock()
    _model: Any = None
    _accuracy: float | None = None
    _engine = "template fallback"

    @classmethod
    def _ensure_model(cls) -> None:
        if cls._model is not None:
            return
        with cls._lock:
            if cls._model is not None:
                return
            try:
                from sklearn.datasets import load_digits
                from sklearn.model_selection import train_test_split
                from sklearn.neural_network import MLPClassifier

                digits = load_digits()
                x_train, x_test, y_train, y_test = train_test_split(
                    digits.data / 16.0,
                    digits.target,
                    test_size=0.20,
                    random_state=17,
                    stratify=digits.target,
                )
                model = MLPClassifier(
                    hidden_layer_sizes=(48, 24),
                    activation="relu",
                    solver="adam",
                    alpha=0.0005,
                    learning_rate_init=0.002,
                    max_iter=350,
                    early_stopping=True,
                    n_iter_no_change=18,
                    random_state=17,
                )
                model.fit(x_train, y_train)
                cls._model = model
                cls._accuracy = round(float(model.score(x_test, y_test)) * 100, 1)
                cls._engine = "scikit-learn MLPClassifier"
            except Exception:
                cls._model = False
                cls._accuracy = None
                cls._engine = "template fallback"

    @staticmethod
    def _template_predict(pixels: list[float]) -> tuple[int, float]:
        # Segment-inspired prototypes provide an explicit no-dependency fallback.
        prototypes = {
            0: [0, 1, 2, 5, 7, 8, 13, 15, 16, 18, 21, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32, 34, 37, 39, 40, 42, 45, 46, 47, 48, 50, 53, 55, 56, 58, 61, 62, 63],
            1: [3, 4, 11, 12, 19, 20, 27, 28, 35, 36, 43, 44, 51, 52, 59, 60],
            2: [1, 2, 3, 4, 5, 6, 14, 21, 29, 34, 41, 49, 57, 58, 59, 60, 61, 62],
            3: [1, 2, 3, 4, 5, 6, 14, 21, 22, 29, 37, 45, 53, 57, 58, 59, 60, 61, 62],
            4: [1, 6, 8, 14, 16, 21, 22, 23, 24, 25, 26, 29, 37, 45, 53, 61],
            5: [1, 2, 3, 4, 5, 6, 8, 16, 17, 18, 19, 20, 21, 29, 37, 45, 53, 57, 58, 59, 60, 61, 62],
            6: [1, 2, 3, 4, 5, 6, 8, 16, 17, 18, 19, 20, 21, 29, 32, 37, 40, 45, 48, 53, 57, 58, 59, 60, 61, 62],
            7: [1, 2, 3, 4, 5, 6, 13, 20, 27, 34, 41, 48, 55, 62],
            8: [2, 3, 4, 5, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 25, 26, 27, 28, 29, 30, 33, 34, 35, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46, 47, 49, 50, 51, 52, 53, 54, 58, 59, 60, 61],
            9: [1, 2, 3, 4, 5, 6, 8, 16, 21, 24, 25, 26, 29, 37, 45, 53, 57, 58, 59, 60, 61, 62],
        }
        active = {index for index, value in enumerate(pixels) if value >= 0.45}
        scores = {digit: len(active & set(cells)) - 0.32 * len(active ^ set(cells)) for digit, cells in prototypes.items()}
        best = max(scores, key=scores.get)
        confidence = max(0.05, min(0.93, 0.35 + scores[best] / 38))
        return best, round(confidence, 2)

    @classmethod
    def predict(cls, values: Any) -> dict[str, Any]:
        if not isinstance(values, list) or len(values) != 64:
            raise ValueError("VisionBench expects an 8 by 8 grid containing exactly 64 numeric values.")
        pixels = [min(1.0, max(0.0, float(value))) for value in values]
        cls._ensure_model()
        if cls._model is False:
            digit, confidence = cls._template_predict(pixels)
            probabilities = [round((1 - confidence) / 9, 3) for _ in range(10)]
            probabilities[digit] = confidence
            return {
                "digit": digit,
                "confidence": confidence,
                "probabilities": probabilities,
                "engine": cls._engine,
                "validation_accuracy": None,
            }
        probabilities = cls._model.predict_proba([pixels])[0]
        digit = int(cls._model.predict([pixels])[0])
        return {
            "digit": digit,
            "confidence": round(float(max(probabilities)), 2),
            "probabilities": [round(float(value), 3) for value in probabilities],
            "engine": cls._engine,
            "validation_accuracy": cls._accuracy,
        }


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "MerchantAILab/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep deployment logs concise and avoid query/body data.
        print(f"[{now_iso()}] {self.address_string()} {fmt % args}")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(serialized)))
        self.end_headers()
        self.wfile.write(serialized)

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValueError("Invalid request body length.") from error
        if length < 1 or length > MAX_BODY_BYTES:
            raise ValueError("Request body must be between 1 and 100,000 bytes.")
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Request body must be valid JSON.") from error
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")
        return body

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/health":
            self._send_json(HTTPStatus.OK, {"status": "ok", "service": "Merchant AI Lab", "time": now_iso()})
            return
        if route.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown API endpoint."})
            return
        if route == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        try:
            payload = self._read_json()
            if route == "/api/fraud/investigate":
                self._send_json(HTTPStatus.OK, investigate_fraud(payload))
            elif route == "/api/growth/recommend":
                self._send_json(HTTPStatus.OK, recommend_merchant_growth(payload))
            elif route == "/api/vision/predict":
                self._send_json(HTTPStatus.OK, DigitPredictor.predict(payload.get("pixels")))
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown API endpoint."})
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception as error:  # pragma: no cover - unexpected errors must not expose internals
            print(f"Unhandled application error: {type(error).__name__}")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The demo could not complete that request."})


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    if not WEB_ROOT.is_dir():
        raise RuntimeError(f"Missing frontend directory: {WEB_ROOT}")
    print(f"Merchant AI Lab listening on http://{host}:{port}")
    ThreadingHTTPServer((host, port), AppHandler).serve_forever()


if __name__ == "__main__":
    main()
