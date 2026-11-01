// vector_search.ts — Embedding-based semantic search via OpenAI + Supabase match_embeddings RPC

import { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

// deno-lint-ignore no-explicit-any
type SB = SupabaseClient<any, any, any>;

export interface VectorMatch {
  id: string;
  entity_type: string;
  entity_id: string;
  content: string;
  // deno-lint-ignore no-explicit-any
  metadata: Record<string, any>;
  similarity: number;
}

const OPENAI_EMBEDDING_MODEL = "text-embedding-3-small";
const OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings";

/**
 * Generate an embedding vector using OpenAI's embedding API.
 */
async function getEmbedding(text: string): Promise<number[]> {
  const apiKey = Deno.env.get("OPENAI_API_KEY");
  if (!apiKey) throw new Error("OPENAI_API_KEY not set");

  const response = await fetch(OPENAI_EMBEDDING_URL, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: OPENAI_EMBEDDING_MODEL,
      input: text,
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`OpenAI embedding API error ${response.status}: ${body}`);
  }

  const json = await response.json();
  return json.data[0].embedding;
}

/**
 * Perform semantic vector search using match_embeddings RPC.
 * Optionally filter by entity_type (e.g. "meetings", "todos").
 */
export async function semanticVectorSearch(
  sb: SB,
  query: string,
  threshold: number = 0.3,
  count: number = 20,
  entityType?: string,
): Promise<VectorMatch[]> {
  const embedding = await getEmbedding(query);

  const rpcParams: Record<string, unknown> = {
    query_embedding: embedding,
    match_threshold: threshold,
    match_count: count,
  };
  if (entityType) {
    rpcParams.filter_entity_type = entityType;
  }

  const { data, error } = await sb.rpc("match_embeddings", rpcParams);

  if (error) throw new Error(`match_embeddings RPC error: ${error.message}`);
  if (!data) return [];

  return data.map((row: {
    id: string;
    entity_type: string;
    entity_id: string;
    content: string;
    // deno-lint-ignore no-explicit-any
    metadata: Record<string, any>;
    similarity: number;
  }) => ({
    id: row.id,
    entity_type: row.entity_type,
    entity_id: row.entity_id,
    content: row.content,
    metadata: row.metadata ?? {},
    similarity: row.similarity,
  }));
}

/**
 * Anchor search: look up embeddings by exact content terms.
 * Useful for supplementing vector search with keyword-based matches from the embeddings table.
 */
export async function anchorSearch(
  sb: SB,
  terms: string[],
  entityType?: string,
): Promise<VectorMatch[]> {
  if (terms.length === 0) return [];

  // Build an OR filter for content ilike matching
  const filters = terms.map((t) => `content.ilike.%${t}%`);

  let query = sb
    .from("embeddings")
    .select("id, entity_type, entity_id, content, metadata")
    .or(filters.join(","));

  if (entityType) {
    query = query.eq("entity_type", entityType);
  }

  const { data, error } = await query.limit(30);

  if (error) {
    console.error(`anchorSearch error: ${error.message}`);
    return [];
  }

  return (data ?? []).map((row: {
    id: string;
    entity_type: string;
    entity_id: string;
    content: string;
    // deno-lint-ignore no-explicit-any
    metadata: Record<string, any>;
  }) => ({
    id: row.id,
    entity_type: row.entity_type,
    entity_id: row.entity_id,
    content: row.content,
    metadata: row.metadata ?? {},
    similarity: 0.5,
  }));
}
