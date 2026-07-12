```
# Fraud Risk Assessment Schema v1
```

## `## Purpose` 

```
This schema defines the structured output of the batch fraud risk analysis
pipeline.
```

```
The AI **must not determine whether fraud occurred.**
```

```
The AI identifies **risk indicators** that warrant further investigation by an
auditor.
```

```
Every finding must reference supporting evidence and, where appropriate, related
procurement regulations.
```

```
---
```

```
# Root Object
```

```
ProjectRiskAssessment
```

```
```python
ProjectRiskAssessment
├── project
├── summary
├── risk_indicators
├── recommendations
├── metadata```
```

```
---
```

## `# Project` 

```
Contains project metadata.
```

```
```python
class ProjectInformation(BaseModel):
```

```
    project_id: str
    project_name: str
    fiscal_year: int
    organization: str
    project_type: str
    procurement_method: str
    project_budget: float
    reference_price: float | None
    winning_vendor: str | None
```
These values come from the database.
The LLM does not generate them.
```

```
---
```

```
# Executive Summary
```

```
```python
class ExecutiveSummary(BaseModel):
```

```
    overall_risk: RiskLevel
```

```
    overall_score: int      # 0-100
    confidence: float       # 0-1
    summary: str
```
```

```
The summary should be concise and factual.
```

```
Never accuse anyone of corruption.
```

```
Use language such as
```

- `requires further investigation` 

- `anomaly detected` 

- `unusual procurement pattern` 

- `potential procurement risk` 

```
---
```

```
# Risk Indicators
```

```
The AI evaluates ONLY these four risk categories.
```

```
```python
```

```
class RiskIndicatorType(Enum):
```

```
    PRICE_HISTORY
```

```
    DUPLICATE_PROJECT
```

```
    VENDOR_CONCENTRATION
```

```
    REFERENCE_PRICE
```
```

```
No additional indicator types should be generated.
```

```
---
```

```
## Risk 1
```

```
PRICE_HISTORY
```

```
Question:
```

```
Has the budget for a similar project increased significantly compared with
previous fiscal years?
```

```
Inputs
```

- `Previous years budget` 

- `Current budget` 

- `Same project category` 

```
Example
```

```
Road construction
```

```
2025 = 1.2M
2026 = 2.8M
```

```
Output
```

- `percentage increase` 

- `explanation` 

- `confidence` 

- `supporting evidence` 

```
---
```

```
## Risk 2
```

```
DUPLICATE_PROJECT
```

```
Question
```

```
Are multiple projects with similar names, objectives, or scopes occurring within
an unusually short period?
```

```
Examples
```

```
Road resurfacing
```

```
Road resurfacing phase 2
```

```
Road repair same village
```

```
Park renovation repeated within 2 months
```

```
Exclude recurring annual events
```

```
Examples
```

```
- Songkran
- Loy Krathong
- National Children's Day
```

```
Output
```

```
- duplicate project list
- explanation
- confidence
- evidence
```

```
---
```

```
## Risk 3
```

```
VENDOR_CONCENTRATION
```

```
Question
```

```
Does the same vendor repeatedly receive contracts for similar projects?
```

```
Especially check
```

- `vehicle maintenance` 

- `same contractor` 

- `same supplier` 

```
Output
```

- `vendor name` 

- `number of projects` 

- `percentage` 

- `explanation` 

- `evidence` 

```
The AI should not conclude favoritism.
```

```
Only report repeated procurement patterns.
```

```
---
```

## `## Risk 4` 

```
REFERENCE_PRICE
```

```
Question
```

`How different is the awarded project price compared to the official` ราคากลาง `? Output` 

- `reference price` 

- `awarded price` 

- `percentage difference` 

- `explanation` 

- `evidence` 

```
The AI should explain whether the deviation appears unusual.
```

```
Do not determine legality.
```

```
---
```

```
# Risk Indicator Object
```

```
```python
class RiskIndicator(BaseModel):
```

```
    indicator: RiskIndicatorType
```

```
    detected: bool
    severity: Severity
    score: int
    confidence: float
    title: str
    explanation: str
    statistics: dict
    evidence: list[Evidence]
```

```
    regulations: list[RegulationReference]
```
```

```
statistics is specific to each indicator.
```

```
Examples
```

```
PRICE_HISTORY
```

```
```json
{
    "previous_budget":1200000,
    "current_budget":2800000,
    "increase_percent":133
}
```
```

```
Vendor
```json
{
    "vendor":"ABC Construction",
    "projects":6,
    "market_share":72
}
```
Reference Price
```

```
```json
{
    "reference_price":1800000,
    "contract_price":2200000,
    "difference_percent":22
}
```
```

```
---
```

## `# Evidence` 

```
Every indicator must cite evidence.
```

```
```python
class Evidence(BaseModel):
    document_id: str
```

```
    document_name: str
```

```
    page: int
    chunk_id: str
    quotation: str
    explanation: str
```
```

```
The quotation should be a direct excerpt from the retrieved document.
```

```
---
```

```
# Regulation Reference
```

```
Optional.
```python
class RegulationReference(BaseModel):
```

```
    law_name: str
```

```
    section: str
    explanation: str
```
```

```
Only include regulations supported by retrieved documents.
Never invent legal citations.
```

```
---
```

## `# Recommendation` 

```
```python
class Recommendation(BaseModel):
    priority: Priority
    action: str
    reason: str
```
```

```
Examples
```

```
- Compare BOQ quantities with site inspection
```

```
- Review procurement committee minutes
```

```
- Request additional quotations
```

```
- Compare historical procurement records
```

```
---
```

## `# Metadata` 

```
```python
class Metadata(BaseModel):
```

```
    schema_version: str
    model_name: str
    prompt_version: str
    processing_time_seconds: float
    generated_at: datetime
```
```

```
---
```

```
# Important Rules
```

`1. Never accuse any person or organization of fraud.` 

`2. Report only observable procurement anomalies.` 

`3. Every indicator must include evidence.` 

`4. Every legal reference must exist in the regulation corpus.` 

`5. Confidence must be between 0 and 1.` 

`6. Risk score must be between 0 and 100.` 

`7. If insufficient evidence exists, mark the indicator as` 

```
detected = false
```

```
instead of guessing.
```

`8. Missing evidence must never be fabricated.` 

`9. The dashboard should be able to display each indicator independently.` 

`10. The output must be valid Pydantic JSON.` 

