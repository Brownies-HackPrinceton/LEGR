from __future__ import annotations

import os
from typing import Any, Dict, List

from openai import AsyncOpenAI

from supabase_client import get_supabase

# Default company ID setup for demo compatibility
_COMPANY_ID = os.getenv("FLUX_COMPANY_ID", "00000001-0000-4000-8000-000000000001")


async def get_chat_history(chat_id: str, limit: int = 10, company_id: str = _COMPANY_ID) -> List[Dict[str, str]]:
    """
    Fetch the short-term chat window for the iMessage thread.
    Returns chronological list of {'role': 'user'|'assistant', 'content': '...'}
    """
    resp = (
        get_supabase()
        .table("message_history")
        .select("role, content")
        .eq("company_id", company_id)
        .eq("chat_id", chat_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    # The database returns them latest first due to order DESC
    # We want to reverse them so they are strictly chronological left to right
    rows = resp.data or []
    history = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    return history


async def save_chat_message(chat_id: str, role: str, content: str, company_id: str = _COMPANY_ID) -> None:
    """Save a single sequence message to the user interaction timeline."""
    try:
        get_supabase().table("message_history").insert({
            "company_id": company_id,
            "chat_id": chat_id,
            "role": role,
            "content": content
        }).execute()
    except Exception as e:
        print(f"[Memory] Failed to save chat message: {e}")


async def get_relevant_memories(user_query: str, company_id: str = _COMPANY_ID, match_count: int = 3, match_threshold: float = 0.5) -> List[Dict[str, Any]]:
    """
    Long-Term Mem (RAG) extractor.
    Creates an embedding of the user's incoming query and calculates cosine similarity
    against all past recorded knowledge/wins using pgvector over the 'memories' table.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[Memory] Warning: OPENAI_API_KEY not set. Cannot run RAG embedding.")
        return []

    client = AsyncOpenAI(api_key=api_key)

    try:
        # Generate the embedding
        response = await client.embeddings.create(
            input=user_query,
            model="text-embedding-3-small"
        )
        query_embedding = response.data[0].embedding

        # Find matching long-term memories via RPC
        rpc_result = get_supabase().rpc(
            "match_memories",
            {
                "query_embedding": query_embedding,
                "match_threshold": match_threshold,
                "match_count": match_count,
                "p_company_id": company_id
            }
        ).execute()
        
        return rpc_result.data or []

    except Exception as e:
        print(f"[Memory] Error fetching relevant memories: {e}")
        return []
