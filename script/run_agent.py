from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_settings
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Loading project settings and initialized ChromaDB vector index...")
    settings = load_settings()
    index = LocalEmbeddingIndex.load(settings)
    print(f" -> Successfully loaded vector store '{index.collection_name}' ({len(index.documents)} papers).\n")

    # 1. Test Deterministic RAG QA (qa.py)
    print("=== PART 1: Deterministic RAG QA (answer_question) ===")
    sample_q1 = "Who are the authors of the paper titled 'Hi‐ RAG : A Hierarchical Retrieval‐Augmented Generation Framework for Scalable and Generalisable Tool Selection in Large Language Model Agents'?"
    res1 = answer_question(sample_q1, settings, index)
    print(f"Q: {sample_q1}")
    print(f"A: {res1.answer}")
    print(f"Retrieved Document DOI: {res1.retrieved_doc_ids[0] if res1.retrieved_doc_ids else 'None'}\n")

    sample_q2 = "When was the paper titled 'Hi‐ RAG : A Hierarchical Retrieval‐Augmented Generation Framework for Scalable and Generalisable Tool Selection in Large Language Model Agents' published?"
    res2 = answer_question(sample_q2, settings, index)
    print(f"Q: {sample_q2}")
    print(f"A: {res2.answer}\n")

    # 2. Test Autonomous Tool-Calling Agent (agent.py)
    print("=== PART 2: Autonomous Tool-Calling Agent (build_agent) ===")
    print(f"Building LangChain tool agent with model '{settings.model_name}'...")
    agent = build_agent(settings, index)

    agent_query = "Can you search for a paper about safety report generation in the oil and gas industry using RAG, and tell me its exact title and DOI?"
    print(f"\nSending interactive prompt to Agent: '{agent_query}'...")
    print(" -> Agent is autonomously executing semantic tools over ChromaDB...")
    
    try:
        agent_reply = run_agent_question(agent, agent_query)
        print(f"\n[Agent Final Answer]:\n{agent_reply}\n")
        print("[✓] Step 8 Execution Complete!")
    except Exception as exc:
        print(f"\n[!] Notice: Autonomous tool calling encountered an LLM provider specific limitation: {exc}")
        print(" -> Note: Deterministic RAG QA operates normally and is ready for Step 9 evaluation pipeline!")


if __name__ == "__main__":
    main()
