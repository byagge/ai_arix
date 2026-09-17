from typing import TypedDict, Annotated, Literal
import operator

from langgraph.graph import StateGraph, END


class AgentState(TypedDict):
    dialog_id: int
    user_message: str
    conversation_history: str
    funnel_stage: str
    rag_context: str
    agent_settings: dict
    orchestrator_decision: dict
    sales_response: str
    followup_response: str
    payment_response: str
    final_response: str
    active_agent: str
    should_respond: bool
    metadata: Annotated[dict, operator.or_]


async def orchestrator_node(state: AgentState) -> AgentState:
    from app.agents.orchestrator import analyze_dialog

    existing = state.get("orchestrator_decision") or {}
    if existing.get("target_agent"):
        decision = existing
    else:
        decision = await analyze_dialog(
            user_message=state["user_message"],
            conversation_history=state["conversation_history"],
            funnel_stage=state["funnel_stage"],
            settings=state["agent_settings"],
        )
    return {
        **state,
        "orchestrator_decision": decision,
        "active_agent": decision.get("target_agent", "sales"),
        "should_respond": decision.get("should_respond", True),
        "metadata": {"new_funnel_stage": decision.get("funnel_stage", state["funnel_stage"])},
    }


async def sales_node(state: AgentState) -> AgentState:
    from app.agents.sales import generate_sales_response

    if state["active_agent"] != "sales":
        return state
    response = await generate_sales_response(
        user_message=state["user_message"],
        conversation_history=state["conversation_history"],
        rag_context=state["rag_context"],
        settings=state["agent_settings"],
        orchestrator_hint=state["orchestrator_decision"],
    )
    return {**state, "sales_response": response, "final_response": response}


async def followup_node(state: AgentState) -> AgentState:
    from app.agents.followup import generate_followup_response

    if state["active_agent"] != "followup":
        return state
    response = await generate_followup_response(
        conversation_history=state["conversation_history"],
        settings=state["agent_settings"],
        followup_number=state.get("metadata", {}).get("followup_number", 1),
    )
    return {**state, "followup_response": response, "final_response": response}


async def payment_node(state: AgentState) -> AgentState:
    from app.agents.payment_agent import generate_payment_response

    if state["active_agent"] != "payment":
        return state
    response, payment_data = await generate_payment_response(
        user_message=state["user_message"],
        conversation_history=state["conversation_history"],
        dialog_id=state["dialog_id"],
        settings=state["agent_settings"],
        orchestrator_hint=state["orchestrator_decision"],
    )
    meta = dict(state.get("metadata", {}))
    meta["payment_data"] = payment_data
    return {**state, "payment_response": response, "final_response": response, "metadata": meta}


def route_agent(state: AgentState) -> Literal["sales", "followup", "payment", "end"]:
    if not state.get("should_respond", True):
        return "end"
    agent = state.get("active_agent", "sales")
    if agent in ("sales", "followup", "payment"):
        return agent
    return "sales"


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("sales", sales_node)
    graph.add_node("followup", followup_node)
    graph.add_node("payment", payment_node)

    graph.set_entry_point("orchestrator")
    graph.add_conditional_edges("orchestrator", route_agent, {
        "sales": "sales",
        "followup": "followup",
        "payment": "payment",
        "end": END,
    })
    graph.add_edge("sales", END)
    graph.add_edge("followup", END)
    graph.add_edge("payment", END)

    return graph.compile()


agent_graph = build_agent_graph()
