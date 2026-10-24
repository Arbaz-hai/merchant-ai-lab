# Merchant AI Lab

**An independent, public, no-secret portfolio demo for controlled fraud-risk investigation and merchant-growth workflows.**

All records, decisions, and model inputs are synthetic. This educational demo is not affiliated with Paytm or any payment provider, and it never connects to real payment rails, customer accounts, or merchant data.

| Demo | What it proves |
| --- | --- |
| **FraudShield** | A controlled financial-risk investigation workflow that checks synthetic transaction, customer/device, merchant, blacklist, velocity, geography, amount, and behavioral signals; it returns an auditor-ready decision with a human-approval boundary. |
| **Merchant Growth Advisor** | Verified-metric analysis with trends, anomalies, forecast assumptions, and no more than three approval-gated growth recommendations. |
| **VisionBench** | A live 8x8 digit-classification API powered by a small neural network trained from scikit-learn's bundled handwritten-digits dataset. |

The application is deliberately dependency-light: it serves both the frontend and API from one Python process, requires no paid model/API key, and uses synthetic merchant data.

## Why this portfolio project

Payment-adjacent agentic AI needs controlled action boundaries, not just a chat interface. The demo makes those boundaries visible:

1. Separate trusted inputs from transaction metadata and external text, which are always treated as untrusted.
2. Use only scoped synthetic lookup tools and deterministic risk/analytics logic.
3. Make risk evidence, policy outcomes, confidence, and limitations visible to an auditor.
4. Create an investigation case only for HIGH or CRITICAL risk; never autonomously block an account or reverse a payment.
5. Keep merchant campaigns as drafts until a merchant explicitly approves them.
6. Keep sensitive fields masked and prohibit protected-class targeting.

It was shaped to complement my research paper, *Comparative Analysis of Transformer Models for Prompt Injection Detection in Autonomous Large Language Model Agents*, published in **Cureus Journal of Computer Science** (October 2026). [DOI: 10.7759/s44389-026-00329-y](https://doi.org/10.7759/s44389-026-00329-y)

## Run locally

```bash
python -m pip install -r requirements.txt
python server.py
```

Open [http://localhost:8000](http://localhost:8000). The backend is available immediately at `GET /api/health`.

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Deployment health check. |
| `POST` | `/api/fraud/investigate` | Produces the strict FraudShield risk decision schema from a synthetic transaction. |
| `POST` | `/api/growth/recommend` | Produces verified metric analysis and at most three approval-gated merchant recommendations. |
| `POST` | `/api/vision/predict` | Classifies an 8x8 drawn digit using the MLP service. |

Example FraudShield request:

```json
{
  "transaction_id": "txn_demo_velocity",
  "untrusted_context": ""
}
```

The FraudShield response always includes `transaction_id`, `risk_score`, `risk_level`, `recommended_action`, `evidence`, `reasoning_summary`, `confidence`, `case_created`, and `human_approval_required`.

Merchant Growth returns the following contract, with no more than three recommendations:

```json
{
  "merchant_id": "...",
  "period": "...",
  "summary": "...",
  "observed_metrics": {},
  "recommendations": [
    {
      "title": "...",
      "action": "...",
      "expected_impact": "...",
      "estimated_cost": "...",
      "risk": "...",
      "confidence": 0.0,
      "requires_approval": true
    }
  ],
  "draft_campaigns": [],
  "data_limitations": []
}
```

## Quality checks

```bash
python -m unittest discover -s tests -v
```

The tests verify risk tiers, prompt-injection isolation, missing-evidence escalation, human approval boundaries, and approval-gated merchant recommendations.

## Free deployment on Render

This repository includes `render.yaml` for a Free Python Web Service. In Render:

1. Create a new **Web Service** from this public repository.
2. Choose the **Free** plan and a region close to your audience.
3. Use `pip install -r requirements.txt` as the build command and `python server.py` as the start command.
4. Set `/api/health` as the health-check endpoint.

Render will supply `PORT`; the application reads it automatically. Free instances may sleep while idle, so the first request can take a short time to wake.

## Safety and scope

- This is an educational portfolio demo, not a payment service or fraud platform.
- No real payment, refund, bank, identity, credential, OTP, PIN, CVV, or personal data is used or transmitted.
- Uploaded text, transaction descriptions, customer messages, and metadata are untrusted; instruction-like content never changes the policy.
- HIGH and CRITICAL outcomes create only simulated investigation cases or reviews. Account blocking, payment reversal, and campaign publication require a human or authorized policy engine.
- Merchant recommendations use synthetic, non-sensitive business data. They do not target protected characteristics and do not guarantee revenue growth.

## Repository layout

```text
.
├── server.py              # API, controlled agents, safety checks, and MLP service
├── web/                   # dependency-free browser interface
├── tests/                 # regression tests for policies and schemas
├── render.yaml            # free Render deployment blueprint
└── requirements.txt       # optional neural-network dependency
```

## License

Released under the [MIT License](LICENSE).
