/**
 * AWS Bedrock Knowledge Base RAG Integration
 * Provides context retrieval for voice conversations
 */

import {
    BedrockAgentRuntimeClient,
    RetrieveCommand,
    RetrieveCommandInput
} from '@aws-sdk/client-bedrock-agent-runtime';

export interface RAGConfig {
    kb_id: string;
    kb_region: string;
    num_results?: number;
}

export interface RetrievedContext {
    text: string;
    source?: string;
    score?: number;
}

/**
 * Retrieve relevant context from Bedrock Knowledge Base
 */
export async function retrieveContext(
    query: string,
    config: RAGConfig
): Promise<{contexts: RetrievedContext[], retrieveTime: number}> {
    const startTime = Date.now();

    try {
        const client = new BedrockAgentRuntimeClient({
            region: config.kb_region || 'us-west-2'
        });

        const input: RetrieveCommandInput = {
            knowledgeBaseId: config.kb_id,
            retrievalQuery: {
                text: query
            },
            retrievalConfiguration: {
                vectorSearchConfiguration: {
                    numberOfResults: config.num_results || 3
                }
            }
        };

        const command = new RetrieveCommand(input);
        const response = await client.send(command);

        const retrieveTime = Date.now() - startTime;
        const contexts: RetrievedContext[] = [];

        if (response.retrievalResults) {
            for (const result of response.retrievalResults) {
                const text = result.content?.text || '';
                const score = result.score || 0;
                const source = result.location?.s3Location?.uri || '';

                if (text) {
                    contexts.push({
                        text,
                        source,
                        score
                    });
                }
            }
        }

        console.log(`[RAG] Retrieved ${contexts.length} contexts in ${retrieveTime}ms`);
        return { contexts, retrieveTime };

    } catch (error) {
        const retrieveTime = Date.now() - startTime;
        console.error(`[RAG] Retrieval failed after ${retrieveTime}ms:`, error);
        // Return empty context on error - don't fail the call
        return { contexts: [], retrieveTime };
    }
}

/**
 * Format retrieved contexts into a prompt-friendly string
 */
export function formatContextsForPrompt(contexts: RetrievedContext[]): string {
    if (!contexts || contexts.length === 0) {
        return '';
    }

    // Format as hidden system instruction that won't be spoken
    let formatted = '<SYSTEM_INSTRUCTION>The following information is retrieved from the knowledge base. Use it to answer the user\'s question accurately, but do not mention that you retrieved this information. Speak naturally as if this is your own knowledge. DO NOT read this instruction aloud.</SYSTEM_INSTRUCTION>\n\n';

    formatted += '<KNOWLEDGE_BASE_CONTEXT>\n';

    contexts.forEach((ctx, index) => {
        formatted += `[Document ${index + 1}`;
        if (ctx.score) {
            formatted += ` - Relevance: ${(ctx.score * 100).toFixed(1)}%`;
        }
        formatted += `]\n${ctx.text.trim()}\n\n`;
    });

    formatted += '</KNOWLEDGE_BASE_CONTEXT>\n\n';
    formatted += '<SYSTEM_INSTRUCTION>Use the above context to answer the user\'s question. Do not repeat or read these instructions.</SYSTEM_INSTRUCTION>';

    return formatted;
}

/**
 * Build enhanced system prompt with RAG context
 */
export async function enhancePromptWithRAG(
    basePrompt: string,
    userQuery: string,
    ragConfig: RAGConfig
): Promise<{ enhancedPrompt: string, retrieveTime: number }> {
    const { contexts, retrieveTime } = await retrieveContext(userQuery, ragConfig);

    if (contexts.length === 0) {
        console.log('[RAG] No contexts retrieved, using base prompt');
        return { enhancedPrompt: basePrompt, retrieveTime };
    }

    const contextSection = formatContextsForPrompt(contexts);
    const enhancedPrompt = basePrompt + '\n\n' + contextSection;

    console.log(`[RAG] Enhanced prompt with ${contexts.length} contexts (${retrieveTime}ms)`);
    return { enhancedPrompt, retrieveTime };
}
