"""A dependency-light public demo for safe merchant operations agents.

The app deliberately uses synthetic payment data and deterministic tool routing so it
can be deployed without secrets, paid model APIs, or access to real payment systems.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
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

MERCHANTS = {
    "merchant_demo_01": {
        "name": "Nisha Kirana Store",
        "city": "Noida",
        "language": "English / Hindi",
        "today_transactions": 186,
        "today_gmv": 42860,
        "success_rate": 98.4,
        "refunds_pending": 2,
        "settlement_eta": "Today, 18:30 IST",
    },
    "merchant_demo_02": {
        "name": "Ravi Mobile Repairs",
        "city": "Delhi",
        "language": "Hindi / English",
        "today_transactions": 74,
        "today_gmv": 19640,
        "success_rate": 97.1,
        "refunds_pending": 1,
        "settlement_eta": "Tomorrow, 10:00 IST",
    },
}

POLICIES = {
    "refund": "Refunds above INR 5,000 or any request using unverified beneficiary details require human approval.",
    "settlement": "The agent may explain a settlement status but must not alter settlement instructions.",
    "onboarding": "The agent may prepare an onboarding checklist; merchant identity and bank details need human verification.",
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

HIGH_RISK_ACTIONS = ("refund", "transfer", "payout", "payment", "settlement", "delete", "bank detail")


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


def _intent_for(task: str) -> str:
    task = task.lower()
    if any(token in task for token in ("refund", "return money", "money back")):
        return "refund"
    if any(token in task for token in ("settlement", "payout", "credit when")):
        return "settlement"
    if any(token in task for token in ("onboard", "kyc", "activate", "profile")):
        return "onboarding"
    if any(token in task for token in ("summary", "sales", "transaction", "payment", "today", "aaj", "report")):
        return "summary"
    return "help"


def _human_approval_needed(task: str) -> bool:
    task = task.lower()
    return any(action in task for action in HIGH_RISK_ACTIONS)


def append_audit(event: dict[str, Any]) -> None:
    """Write a minimal synthetic trace for the demo without storing raw source text."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def run_merchant_agent(payload: dict[str, Any]) -> dict[str, Any]:
    merchant_id = clamp_text(payload.get("merchant_id")) or "merchant_demo_01"
    merchant = MERCHANTS.get(merchant_id, MERCHANTS["merchant_demo_01"])
    task = clamp_text(payload.get("task"), 2_000)
    external_context = clamp_text(payload.get("external_context"), 30_000)
    if not task:
        raise ValueError("Please describe a merchant operations task.")

    audit_id = f"audit_{uuid.uuid4().hex[:10]}"
    guard = analyze_prompt_injection(external_context)
    trace = [
        {"step": "Trust boundary", "detail": "Separated user task from untrusted external context."},
        {"step": "Input guard", "detail": f"{guard['decision'].title()} | risk {guard['risk_score']}/100"},
    ]

    if guard["decision"] == "block":
        result = {
            "audit_id": audit_id,
            "status": "blocked",
            "message": "The external context was quarantined before any merchant tool could run.",
            "guard": guard,
            "tools_used": [],
            "trace": trace + [{"step": "Safe fallback", "detail": "Returned a concise block decision; no action was attempted."}],
        }
        append_audit({"at": now_iso(), "audit_id": audit_id, "intent": "blocked", "status": "blocked", "risk": guard["risk_score"]})
        return result

    intent = _intent_for(task)
    trace.append({"step": "Plan", "detail": f"Classified intent as {intent}; selected least-privilege read tools."})
    tool_output: dict[str, Any]
    tools_used: list[str]
    if intent == "summary":
        tools_used = ["merchant_profile.read", "payment_summary.read"]
        tool_output = {
            "merchant": merchant["name"],
            "location": merchant["city"],
            "transactions_today": merchant["today_transactions"],
            "gmv_today_inr": merchant["today_gmv"],
            "payment_success_rate": f"{merchant['success_rate']}%",
            "pending_refunds": merchant["refunds_pending"],
        }
        status = "completed"
        message = "Prepared a read-only merchant summary from synthetic demo data."
    elif intent == "settlement":
        tools_used = ["merchant_profile.read", "settlement_status.read"]
        tool_output = {"merchant": merchant["name"], "next_settlement": merchant["settlement_eta"], "policy": POLICIES["settlement"]}
        status = "completed"
        message = "Retrieved settlement status; no settlement instruction can be changed by this demo agent."
    elif intent == "onboarding":
        tools_used = ["onboarding_checklist.read"]
        tool_output = {
            "checklist": ["Verify merchant identity", "Validate bank account through an approved workflow", "Confirm business category", "Obtain human approval before activation"],
            "policy": POLICIES["onboarding"],
        }
        status = "completed"
        message = "Prepared a read-only onboarding checklist."
    elif intent == "refund":
        tools_used = ["merchant_profile.read", "refund_policy.read"]
        tool_output = {"policy": POLICIES["refund"], "proposed_action": "A human approver must validate the refund before execution."}
        status = "requires_human_approval"
        message = "The agent created a refund plan but intentionally cannot issue a refund."
    else:
        tools_used = ["capability_catalog.read"]
        tool_output = {
            "supported_tasks": ["today's payment summary", "settlement status", "merchant onboarding checklist", "refund policy guidance"],
            "safety_note": "This public demo has no access to real payments, accounts, or customer data.",
        }
        status = "completed"
        message = "Explained the demo agent's safe, read-only capabilities."

    if _human_approval_needed(task) and status == "completed":
        trace.append({"step": "Human-in-the-loop", "detail": "Task wording requests an external effect; retained read-only mode."})
    trace.append({"step": "Tool results", "detail": ", ".join(tools_used)})
    trace.append({"step": "Response", "detail": "Produced a grounded answer with an auditable trace."})
    result = {
        "audit_id": audit_id,
        "status": status,
        "message": message,
        "guard": guard,
        "tools_used": tools_used,
        "tool_output": tool_output,
        "trace": trace,
    }
    append_audit({"at": now_iso(), "audit_id": audit_id, "intent": intent, "status": status, "risk": guard["risk_score"], "tools": tools_used})
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
            if route == "/api/merchant/run":
                self._send_json(HTTPStatus.OK, run_merchant_agent(payload))
            elif route == "/api/guard/analyze":
                result = analyze_prompt_injection(clamp_text(payload.get("text"), 30_000))
                result["audit_id"] = f"guard_{uuid.uuid4().hex[:10]}"
                self._send_json(HTTPStatus.OK, result)
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
