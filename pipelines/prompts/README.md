# Thai prompt templates (versioned)

Every prompt the pipelines send to an LLM lives here as a versioned file —
**never as an inline string in code.** `RiskResult.prompt_version` records which
version produced each result (e.g. `risk_scoring/v1`).

Planned layout (Phase 2):

```
prompts/
├── risk_scoring/          # one template per RiskFactorType, plus the aggregator
│   └── v1/
├── regulation_linkage/
│   └── v1/
├── feedback_sentiment/
│   └── v1/
└── chat/                  # RAG system prompt with citation instructions
    └── v1/
```

Rules:
- Thai first; UTF-8 always.
- Every template defines the assistant as a risk-flagging aide for human
  auditors — neutral phrasing, "flag, never accuse", final judgment rests
  with the auditor.
- Structured-output prompts pair with `schemas.RiskAssessment` via
  vLLM `guided_json` at temperature 0.
- Changing a template = new version directory; old versions are never edited,
  so Langfuse traces stay reproducible.
