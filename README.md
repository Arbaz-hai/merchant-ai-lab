# Merchant AI Lab

**A public, no-secret portfolio demo for safe agentic workflows in merchant operations.**

Merchant AI Lab contains three working, browser-accessible demonstrations designed around payment-adjacent workflows without claiming access to any real payment rail, customer account, or merchant data.

| Demo | What it proves |
| --- | --- |
| **VyaparSathi** | A multilingual merchant-operations agent that routes read-only payment, settlement, onboarding, and refund-policy tasks through scoped tools. |
| **AgentSentinel** | A prompt-injection guard that scores untrusted external context, quarantines dangerous instructions, and records an auditable safe fallback. |
| **VisionBench** | A live 8x8 digit-classification API powered by a small neural network trained from scikit-learn's bundled handwritten-digits dataset. |

The application is deliberately dependency-light: it serves both the frontend and API from one Python process, requires no paid model/API key, and uses synthetic merchant data.

## Why this portfolio project

Payment and merchant AI needs more than a chat interface. The demo makes the boundaries visible:

1. Separate a user's task from untrusted external content.
2. Assess prompt-injection risk before a tool can run.
3. Plan with least-privilege, read-only tools.
4. Require human approval for requests that could have an external effect.
5. Return an auditable trace instead of hidden tool behavior.

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
| `POST` | `/api/merchant/run` | Runs the scoped merchant agent. |
| `POST` | `/api/guard/analyze` | Analyses untrusted text for prompt-injection signals. |
| `POST` | `/api/vision/predict` | Classifies an 8x8 drawn digit using the MLP service. |

Example merchant request:

```json
{
  "merchant_id": "merchant_demo_01",
  "task": "Show me today's payment summary.",
  "external_context": ""
}
```

## Quality checks

```bash
python -m unittest discover -s tests -v
```

The tests verify prompt-injection blocking, safe tool isolation, read-only task routing, and the human-approval gate.

## Free deployment on Render

This repository includes `render.yaml` for a Free Python Web Service. In Render:

1. Create a new **Web Service** from this public repository.
2. Choose the **Free** plan and a region close to your audience.
3. Use `pip install -r requirements.txt` as the build command and `python server.py` as the start command.
4. Set `/api/health` as the health-check endpoint.

Render will supply `PORT`; the application reads it automatically. Free instances may sleep while idle, so the first request can take a short time to wake.

## Safety and scope

- This is an educational portfolio demo, not a payment service.
- Merchant records are synthetic and no payment, refund, bank, identity, or personal data is transmitted.
- The prompt guard is a transparent rule-based prototype, not a claim of production-grade security or a replacement for defense-in-depth.
- Refund-like tasks intentionally stop at a human-approval boundary.

## Repository layout

```text
.
├── server.py              # API, agent orchestration, guardrail, and MLP service
├── web/                   # dependency-free browser interface
├── tests/                 # safe-routing and prompt-injection tests
├── render.yaml            # free Render deployment blueprint
└── requirements.txt       # optional neural-network dependency
```

## License

Released under the [MIT License](LICENSE).
