# AI Query Service — Design Document

- **Component:** AI Query Service
- **Owner:** Person 2 (Alexander)
- **Framework:** FastAPI + Ollama (local)
- **MCP Transport:** stdio subprocess (launches Product MCP + Stock MCP on startup)
- **Status:** design — not yet implemented

External contracts: `docs/api_contracts.md` §8–11.

---

## 1. Purpose

Receives natural-language questions from the public interface, routes them through an Ollama-powered agent with MCP tool access, and returns grounded, structured answers. Never invents data.

```
Anonymous Customer → Public Interface → AI Query Service → Product MCP → Product API
                                                       → Stock MCP  → PostgreSQL
```

---

## 2. Directory Structure

```
ai_service/
├── main.py                # FastAPI app, lifespan (MCP startup/shutdown), /health
├── api/
│   └── routes.py          # POST /questions
├── agents/
│   ├── tool_loop.py       # Ollama tool-calling loop (max 5 rounds, 30s timeout)
│   ├── tool_registry.py   # MCP tool discovery → Ollama tool definitions
│   └── mcp_client.py      # MCP session manager (stdio subprocess lifecycle)
├── prompts/
│   └── system_prompt.txt  # Agent grounding rules
├── models/
│   ├── request.py         # QuestionRequest (question: str, 1–1000 chars)
│   └── response.py        # QuestionResponse (status, answer, data)
├── config.py
├── requirements.txt
└── tests/
    ├── conftest.py
    ├── test_routes.py
    └── fixtures/
        ├── mock_product_mcp.py
        └── mock_stock_mcp.py
```

---

## 3. Endpoint

### `POST /questions` — public, no auth

**Request:**
```json
{"question": "Which branch has three units of product X?"}
```
Validated: non-empty string, max 1000 chars.

**Response statuses (all HTTP 200 except infrastructure failures):**

| `status` | Meaning | HTTP |
|---|---|---|
| `success` | Full answer from real data | 200 |
| `partial` | Some data found, some missing | 200 |
| `unavailable` | Tools returned nothing useful | 200 |
| `unsupported` | Question out of scope | 200 |
| `error` | MCP/Ollama infrastructure failure | 503 |

```json
// Success
{"status": "success", "answer": "The product is available in Toulon with 8 units.",
 "data": {"products": [{"external_product_id": "product-123", "name": "Example product"}],
          "branches": [{"branch_id": 2, "branch_name": "Toulon", "available_quantity": 8}]}}

// Unavailable
{"status": "unavailable", "answer": "I do not have enough information to answer this question.", "data": {}}

// Unsupported
{"status": "unsupported", "answer": "This question is outside the supported inventory scope.",
 "data": {"supported_question_types": ["product_details", "product_availability", "branch_inventory", "shopping_list"]}}

// Error
{"status": "error", "answer": "The inventory service is temporarily unavailable. Please try again.", "data": {}}
```

---

## 4. Agent Tool-Calling Loop

```
POST /questions
  │
  ▼
Build messages: [system_prompt, user_question]
  │
  ▼
Send to Ollama POST /api/chat (with tool definitions)
  │
  ├── Ollama returns tool_call(s) ──► Execute via MCP client ──► Append result to messages ──┐
  │                                                                                          │
  └── Ollama returns final answer ──► Return structured response ◄───────────────────────────┘
```

**Constraints:**
- Max 5 tool-calling rounds
- 30-second total timeout
- After timeout or max rounds: use last response as answer, or return `unavailable` if none

**Startup:** On FastAPI lifespan start, launch Product MCP and Stock MCP as stdio subprocesses. Call `list_tools()` on each, build Ollama-compatible function definitions. On shutdown, terminate subprocesses.

---

## 5. System Prompt (`prompts/system_prompt.txt`)

This is the core grounding mechanism. The model sees this as the first message on every request.

```
You are an inventory assistant for a retail company with multiple physical branches.

## RULES
1. ONLY answer using data returned by tools. NEVER invent products, descriptions, prices, branches, quantities, or availability.
2. If tools don't provide enough information, say: "I do not have enough information to answer this question."
3. If the question is not about products or stock, return unsupported and list supported types.
4. When a product is out of stock everywhere, clearly state that. An empty tool result means no stock.
5. Always include branch name and available quantity when presenting stock data.
6. For shopping lists, use find_branches_for_shopping_list. Present its structured result clearly.
7. Keep answers concise and factual. No marketing, recommendations, or opinions.

## SUPPORTED QUESTION TYPES
- product_details: "What is product X?"
- product_availability: "Where can I find product X?" / "Is product Y in stock?"
- branch_inventory: "What products are available in Toulon?"
- shopping_list: "I need 3 of X and 2 of Y — where should I go?"

## AVAILABLE TOOLS
Product tools: list_products, get_product_details
Stock tools: list_branch_stock, get_stock_for_product, find_branches_with_stock, find_branches_for_shopping_list

## EXAMPLES
Q: "Where can I find product-123?"
→ Call get_stock_for_product("product-123"), answer with branch names and quantities.

Q: "What's available in Marseille?"
→ Call list_branch_stock for Marseille's branch_id, list the products.

Q: "I need 2 units of product-123 and 1 unit of product-456"
→ Call find_branches_for_shopping_list with both items, present the visit plan.
```

---

## 6. Response Models

```python
class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)

class QuestionResponse(BaseModel):
    status: Literal["success", "partial", "unavailable", "unsupported", "error"]
    answer: str
    data: dict = {}
```

---

## 7. Configuration

| Variable | Required | Default |
|---|---|---|
| `OLLAMA_HOST` | No | `http://localhost:11434` |
| `OLLAMA_MODEL` | Yes | — |
| `OLLAMA_TIMEOUT` | No | `30` |
| `OLLAMA_MAX_TOOL_ROUNDS` | No | `5` |
| `PRODUCT_MCP_COMMAND` | No | `python -m product_mcp_server.server` |
| `STOCK_MCP_COMMAND` | No | `python -m stock_mcp_server.server` |
| `AI_SERVICE_PORT` | No | `8000` |
| `CLIENT_ORIGIN` | No | `*` |

---

## 8. Error Handling

| Scenario | HTTP | `status` |
|---|---|---|
| Empty/oversized question | 400 | — (FastAPI validation) |
| Ollama unavailable | 503 | `error` |
| Ollama timeout | 504 | `error` |
| Product MCP unavailable | 503 | `error` (can still answer stock-only if Stock MCP works) |
| Stock MCP unavailable | 503 | `error` (can still answer product-only if Product MCP works) |
| Both MCPs unavailable | 503 | `error` |
| No tools called, no answer | 200 | `unavailable` |
| Off-topic question | 200 | `unsupported` |

---

## 9. CORS

Allow `POST`, `GET` from configured `CLIENT_ORIGIN`. Headers: `Content-Type` only.

---

## 10. Health

```
GET /health → {"status": "ok"}
```

---

## 11. Docker Compose

```yaml
ai_service:
  build: ./ai_service
  ports: ["${AI_SERVICE_PORT:-8000}:8000"]
  environment:
    - OLLAMA_HOST=http://ollama:11434
    - OLLAMA_MODEL=${OLLAMA_MODEL}
    - CLIENT_ORIGIN=http://client_web:${CLIENT_WEB_PORT:-3000}
  depends_on:
    ollama:
      condition: service_healthy
```

---

## 12. Dependencies

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
mcp>=1.0.0
httpx>=0.27.0
pydantic>=2.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

No LangChain/LlamaIndex — Ollama native API is sufficient.

---

## 13. Definition of Done

- [ ] `POST /questions` validates and processes requests
- [ ] Ollama tool-calling loop selects correct tools for each question type
- [ ] All 4 question types produce grounded answers from real MCP data
- [ ] No invented products, branches, quantities, or availability
- [ ] `unavailable` returned when tools provide no data
- [ ] `unsupported` returned for out-of-scope questions
- [ ] MCP and Ollama failures degrade gracefully (no crashes)
- [ ] CORS configured for public client
- [ ] Integration tests pass with mock MCP servers
- [ ] Manual tests pass with real Ollama + MCP servers
- [ ] Reviewed by Person 1 or Person 3
