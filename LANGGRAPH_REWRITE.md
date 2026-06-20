# LangGraph Rewrite Notes

## Goal

Keep the existing FastAPI and Vue contracts unchanged, and replace only the
backend planning core with a LangGraph workflow.

## Current API Contract

The frontend still calls:

```text
POST /api/trip/plan
```

Input remains `TripRequest`, and output remains `TripPlanResponse` with a
`TripPlan` payload.

## New Backend Flow

The new workflow lives in:

```text
backend/app/graphs/trip_graph.py
```

Graph nodes:

```text
START
  -> search_attractions
  -> get_weather
  -> search_hotels
  -> generate_plan
  -> validate_plan
  -> repair_plan, only when validation fails once
  -> END
```

## Why LangGraph

This project is naturally a multi-step workflow. LangGraph makes each step
explicit and inspectable:

- `TripGraphState` carries request data, map results, model output, validation
  status, and errors.
- Each node has one responsibility.
- `validate_plan` uses the existing Pydantic `TripPlan` model as the contract.
- `repair_plan` demonstrates conditional routing and output recovery.
- A fallback plan keeps the API usable when map data, model access, or validation
  fails.

## Interview Talking Points

1. I preserved the external API contract and refactored only the orchestration
   layer.
2. The original version used sequential SimpleAgent calls; the rewrite uses a
   typed graph state and explicit workflow nodes.
3. LangChain is used for model integration through `ChatOpenAI`; LangGraph owns
   orchestration and state transitions.
4. Pydantic validation prevents malformed LLM JSON from leaking to the frontend.
5. The graph has a repair path and a deterministic fallback path, so failures are
   handled intentionally.

## Run

Install backend dependencies:

```bash
cd backend
pip install -r requirements.txt
```

Then start the backend:

```bash
python run.py
```

Required environment variables:

```text
AMAP_API_KEY=...
LLM_API_KEY=...
LLM_BASE_URL=...
LLM_MODEL_ID=...
```

