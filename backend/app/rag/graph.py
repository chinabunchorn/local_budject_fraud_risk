"""LangGraph RAG state graph — the deterministic retrieval half of the chat path.

Nodes run in sequence: embed the Thai question (BGE-M3 via TEI) → pgvector top-k
over documents *and* regulations → BGE-reranker → assemble the citation-carrying
prompt. The streamed generation itself is NOT a graph node — it runs in the SSE
endpoint so token-level sentence-gating, guardrails, and telemetry have direct
control over the stream. The graph produces the messages + the labeled context;
the endpoint does the talking.

Each node is timed into the request's `StreamTelemetry` (embed / retrieve /
rerank / assemble stage durations), which is what the optimization story charts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.prompt import build_messages
from app.rag.retrieval import (
    RetrievedContext,
    apply_rerank,
    retrieve_candidates,
)
from app.services.tei import TEIClient
from app.services.telemetry import StreamTelemetry


class ChatState(TypedDict, total=False):
    question: str
    history: list[dict[str, str]]
    qvec: list[float]
    candidates: list[RetrievedContext]
    context: list[RetrievedContext]
    messages: list[dict[str, str]]


@dataclass
class ChatDeps:
    session: AsyncSession
    tei: TEIClient
    telemetry: StreamTelemetry
    top_k: int
    rerank_top_n: int


def build_chat_graph(deps: ChatDeps):
    async def embed_query(state: ChatState) -> ChatState:
        with deps.telemetry.stage("embed"):
            qvec = await deps.tei.embed(state["question"])
        return {"qvec": qvec}

    async def retrieve(state: ChatState) -> ChatState:
        with deps.telemetry.stage("retrieve"):
            candidates = await retrieve_candidates(
                deps.session, state["qvec"], deps.top_k
            )
        return {"candidates": candidates}

    async def rerank(state: ChatState) -> ChatState:
        candidates = state["candidates"]
        with deps.telemetry.stage("rerank"):
            if candidates:
                scores = await deps.tei.rerank(
                    state["question"], [c.text for c in candidates]
                )
                context = apply_rerank(candidates, scores, deps.rerank_top_n)
            else:
                context = []
        return {"context": context}

    async def assemble(state: ChatState) -> ChatState:
        with deps.telemetry.stage("assemble"):
            messages = build_messages(
                state["question"], state["history"], state["context"]
            )
        return {"messages": messages}

    graph = StateGraph(ChatState)
    graph.add_node("embed_query", embed_query)
    graph.add_node("retrieve", retrieve)
    graph.add_node("rerank", rerank)
    graph.add_node("assemble", assemble)
    graph.add_edge(START, "embed_query")
    graph.add_edge("embed_query", "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "assemble")
    graph.add_edge("assemble", END)
    return graph.compile()


async def run_retrieval(
    deps: ChatDeps, question: str, history: list[dict[str, str]]
) -> ChatState:
    """Run the retrieval graph; returns the final state (messages + context)."""
    graph = build_chat_graph(deps)
    return await graph.ainvoke({"question": question, "history": history})
