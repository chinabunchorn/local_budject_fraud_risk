#!/bin/bash
# ============================================================================
# End-to-end smoke test through the tunnel (Phase 1 exit-gate check).
# RUN ON THE APP VM with tunnel.sh already up.
#
# 1. /v1/models answers            -> tunnel + server alive
# 2. Thai streamed chat completion -> the tracer bullet
# 3. guided_json with a closed risk_level enum -> decode-time lock works
# ============================================================================
set -euo pipefail

BASE="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
MODEL="${VLLM_CHAT_MODEL:-scb10x/typhoon2.5-qwen3-30b-a3b}"

echo ">>> [1/3] GET /models"
curl -sf "$BASE/models" | head -c 400; echo

echo ">>> [2/3] Thai chat completion (streaming)"
curl -sf "$BASE/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "'"$MODEL"'",
        "stream": true,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "สวัสดีครับ ช่วยแนะนำตัวสั้นๆ"}]
    }' | head -20

echo ">>> [3/3] guided_json — risk_level must be enum-locked"
curl -sf "$BASE/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "'"$MODEL"'",
        "temperature": 0,
        "max_tokens": 128,
        "messages": [{"role": "user", "content": "ประเมินระดับความเสี่ยงของโครงการตัวอย่างนี้: งบประมาณ 500,000 บาท จัดซื้อครุภัณฑ์"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "risk_probe",
                "schema": {
                    "type": "object",
                    "properties": {
                        "risk_level": {
                            "type": "string",
                            "enum": ["LOW", "MEDIUM", "HIGH", "REQUIRES_INVESTIGATION"]
                        }
                    },
                    "required": ["risk_level"],
                    "additionalProperties": false
                }
            }
        }
    }'
echo
echo ">>> smoke test passed"
