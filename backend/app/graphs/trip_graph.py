"""LangGraph-based trip planning workflow.

This module keeps the public API contract unchanged: callers still pass a
TripRequest and receive a TripPlan. Internally, the planning flow is explicit:
search attractions, fetch weather, search hotels, generate a plan, validate it,
and optionally repair malformed model output.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TypedDict

from ..config import get_settings
from ..models.schemas import (
    Attraction,
    Budget,
    DayPlan,
    Hotel,
    Location,
    Meal,
    TripPlan,
    TripRequest,
    WeatherInfo,
)
from ..services.amap_service import get_amap_service


class TripGraphState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    request: TripRequest
    attractions_raw: str
    weather_raw: str
    hotels_raw: str
    planner_response: str
    plan: TripPlan
    errors: List[str]
    validated: bool
    repair_attempts: int


class LangGraphTripPlanner:
    """Trip planner implemented as a LangGraph state machine."""

    def __init__(self):
        self.graph = self._build_graph()

    def plan_trip(self, request: TripRequest) -> TripPlan:
        """Run the graph and return a validated TripPlan."""
        initial_state: TripGraphState = {
            "request": request,
            "errors": [],
            "validated": False,
            "repair_attempts": 0,
        }
        final_state = self.graph.invoke(initial_state)
        plan = final_state.get("plan")
        if isinstance(plan, TripPlan):
            return plan
        return self._create_fallback_plan(request, final_state.get("errors", []))

    def _build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise ImportError(
                "LangGraph is not installed. Run `pip install -r backend/requirements.txt` "
                "after the requirements update."
            ) from exc

        graph = StateGraph(TripGraphState)
        graph.add_node("search_attractions", self._search_attractions_node)
        graph.add_node("get_weather", self._get_weather_node)
        graph.add_node("search_hotels", self._search_hotels_node)
        graph.add_node("generate_plan", self._generate_plan_node)
        graph.add_node("validate_plan", self._validate_plan_node)
        graph.add_node("repair_plan", self._repair_plan_node)

        graph.add_edge(START, "search_attractions")
        graph.add_edge("search_attractions", "get_weather")
        graph.add_edge("get_weather", "search_hotels")
        graph.add_edge("search_hotels", "generate_plan")
        graph.add_edge("generate_plan", "validate_plan")
        graph.add_conditional_edges(
            "validate_plan",
            self._route_after_validation,
            {
                "repair": "repair_plan",
                "end": END,
            },
        )
        graph.add_edge("repair_plan", "validate_plan")
        return graph.compile()

    def _search_attractions_node(self, state: TripGraphState) -> TripGraphState:
        request = state["request"]
        keyword = request.preferences[0] if request.preferences else "scenic spot"
        result = self._call_amap_tool(
            "maps_text_search",
            {
                "keywords": keyword,
                "city": request.city,
                "citylimit": "true",
            },
        )
        return self._merge_state(
            state,
            attractions_raw=result or f"No attraction search result for {request.city}.",
        )

    def _get_weather_node(self, state: TripGraphState) -> TripGraphState:
        request = state["request"]
        result = self._call_amap_tool("maps_weather", {"city": request.city})
        return self._merge_state(
            state,
            weather_raw=result or f"No weather result for {request.city}.",
        )

    def _search_hotels_node(self, state: TripGraphState) -> TripGraphState:
        request = state["request"]
        keywords = f"{request.accommodation} hotel"
        result = self._call_amap_tool(
            "maps_text_search",
            {
                "keywords": keywords,
                "city": request.city,
                "citylimit": "true",
            },
        )
        return self._merge_state(
            state,
            hotels_raw=result or f"No hotel search result for {request.city}.",
        )

    def _generate_plan_node(self, state: TripGraphState) -> TripGraphState:
        request = state["request"]
        prompt = self._build_planning_prompt(state)
        response = self._invoke_llm(prompt)
        if not response:
            plan = self._create_fallback_plan(
                request,
                self._append_error(state, "LLM returned an empty response."),
            )
            return self._merge_state(
                state,
                planner_response="",
                plan=plan,
                validated=True,
            )
        return self._merge_state(state, planner_response=response)

    def _validate_plan_node(self, state: TripGraphState) -> TripGraphState:
        request = state["request"]
        response = state.get("planner_response", "")
        try:
            data = self._extract_json(response)
            plan = TripPlan(**data)
            return self._merge_state(state, plan=plan, validated=True)
        except Exception as exc:
            errors = self._append_error(state, f"TripPlan validation failed: {exc}")
            if state.get("repair_attempts", 0) > 0:
                plan = self._create_fallback_plan(request, errors)
                return self._merge_state(
                    state,
                    plan=plan,
                    errors=errors,
                    validated=False,
                )
            return self._merge_state(state, errors=errors, validated=False)

    def _repair_plan_node(self, state: TripGraphState) -> TripGraphState:
        prompt = self._build_repair_prompt(state)
        response = self._invoke_llm(prompt)
        return self._merge_state(
            state,
            planner_response=response,
            repair_attempts=state.get("repair_attempts", 0) + 1,
        )

    def _route_after_validation(self, state: TripGraphState) -> str:
        if state.get("validated"):
            return "end"
        if state.get("repair_attempts", 0) >= 1:
            return "end"
        return "repair"

    def _build_planning_prompt(self, state: TripGraphState) -> str:
        request = state["request"]
        preferences = ", ".join(request.preferences) if request.preferences else "none"
        extra = request.free_text_input or "none"

        return f"""
You are a professional travel planner. Create a practical trip plan in Chinese.

Return JSON only. Do not wrap it in Markdown.

Required JSON schema:
{json.dumps(TripPlan.model_json_schema(), ensure_ascii=False)}

User request:
- city: {request.city}
- start_date: {request.start_date}
- end_date: {request.end_date}
- travel_days: {request.travel_days}
- transportation: {request.transportation}
- accommodation: {request.accommodation}
- preferences: {preferences}
- extra_requirements: {extra}

Amap attraction search result:
{state.get("attractions_raw", "")}

Amap weather result:
{state.get("weather_raw", "")}

Amap hotel search result:
{state.get("hotels_raw", "")}

Rules:
1. Include exactly {request.travel_days} day objects.
2. Each day should include 2-3 attractions, breakfast, lunch, dinner, and a hotel.
3. Use numeric longitude and latitude values. If map data is incomplete, use plausible city-level coordinates and explain uncertainty in descriptions.
4. Include budget totals.
5. Temperature fields must be integers.
"""

    def _build_repair_prompt(self, state: TripGraphState) -> str:
        return f"""
The previous output failed validation for this Pydantic TripPlan schema.
Return corrected JSON only. Do not include Markdown or explanations.

Validation errors:
{chr(10).join(state.get("errors", []))}

Required JSON schema:
{json.dumps(TripPlan.model_json_schema(), ensure_ascii=False)}

Previous output:
{state.get("planner_response", "")}
"""

    def _invoke_llm(self, prompt: str) -> str:
        try:
            model = self._get_chat_model()
            if model is None:
                return ""
            result = model.invoke(prompt)
            return getattr(result, "content", str(result))
        except Exception as exc:
            print(f"LangGraph planner LLM call failed: {exc}")
            return ""

    def _get_chat_model(self):
        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None

        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ImportError(
                "langchain-openai is not installed. Run `pip install -r backend/requirements.txt`."
            ) from exc

        settings = get_settings()
        model_name = os.getenv("LLM_MODEL_ID") or os.getenv("OPENAI_MODEL") or settings.openai_model
        base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or settings.openai_base_url
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.4,
        )

    def _call_amap_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        try:
            service = get_amap_service()
            result = service.mcp_tool.run(
                {
                    "action": "call_tool",
                    "tool_name": tool_name,
                    "arguments": arguments,
                }
            )
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return f"Amap tool {tool_name} failed: {exc}"

    def _extract_json(self, response: str) -> Dict[str, Any]:
        text = response.strip()
        if text.startswith("```json"):
            text = text[7:]
            text = text.split("```", 1)[0].strip()
        elif text.startswith("```"):
            text = text[3:]
            text = text.split("```", 1)[0].strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in planner response.")
        return json.loads(text[start : end + 1])

    def _create_fallback_plan(self, request: TripRequest, errors: Optional[List[str]] = None) -> TripPlan:
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        days: List[DayPlan] = []

        for day_index in range(request.travel_days):
            current_date = start_date + timedelta(days=day_index)
            attractions = [
                Attraction(
                    name=f"{request.city} attraction {idx + 1}",
                    address=f"{request.city}",
                    location=Location(
                        longitude=116.397128 + day_index * 0.01 + idx * 0.005,
                        latitude=39.916527 + day_index * 0.01 + idx * 0.005,
                    ),
                    visit_duration=120,
                    description="Fallback attraction generated because the graph could not produce a validated plan.",
                    category="attraction",
                    ticket_price=0,
                )
                for idx in range(2)
            ]
            meals = [
                Meal(type="breakfast", name="Local breakfast", description="Simple local breakfast.", estimated_cost=30),
                Meal(type="lunch", name="Local lunch", description="Convenient lunch near attractions.", estimated_cost=60),
                Meal(type="dinner", name="Local dinner", description="Dinner with local dishes.", estimated_cost=90),
            ]
            hotel = Hotel(
                name=f"{request.city} recommended hotel",
                address=f"{request.city}",
                location=Location(longitude=116.397128, latitude=39.916527),
                price_range="300-500",
                rating="4.3",
                distance="Near main attractions",
                type=request.accommodation,
                estimated_cost=400,
            )
            days.append(
                DayPlan(
                    date=current_date.strftime("%Y-%m-%d"),
                    day_index=day_index,
                    description=f"Fallback itinerary for day {day_index + 1}.",
                    transportation=request.transportation,
                    accommodation=request.accommodation,
                    hotel=hotel,
                    attractions=attractions,
                    meals=meals,
                )
            )

        total_hotels = 400 * request.travel_days
        total_meals = 180 * request.travel_days
        total_transportation = 80 * request.travel_days
        budget = Budget(
            total_attractions=0,
            total_hotels=total_hotels,
            total_meals=total_meals,
            total_transportation=total_transportation,
            total=total_hotels + total_meals + total_transportation,
        )
        error_note = f" Graph errors: {'; '.join(errors)}" if errors else ""

        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[
                WeatherInfo(
                    date=(start_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                    day_weather="unknown",
                    night_weather="unknown",
                    day_temp=0,
                    night_temp=0,
                    wind_direction="unknown",
                    wind_power="unknown",
                )
                for i in range(request.travel_days)
            ],
            overall_suggestions=(
                "This fallback plan keeps the API usable, but real map or LLM data was unavailable."
                + error_note
            ),
            budget=budget,
        )

    def _append_error(self, state: TripGraphState, error: str) -> List[str]:
        return [*state.get("errors", []), error]

    def _merge_state(self, state: TripGraphState, **updates: Any) -> TripGraphState:
        return {**state, **updates}


_langgraph_trip_planner: Optional[LangGraphTripPlanner] = None


def get_langgraph_trip_planner() -> LangGraphTripPlanner:
    """Return the singleton LangGraph trip planner."""
    global _langgraph_trip_planner
    if _langgraph_trip_planner is None:
        _langgraph_trip_planner = LangGraphTripPlanner()
    return _langgraph_trip_planner

