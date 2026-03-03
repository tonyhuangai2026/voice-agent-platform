import { DefaultToolSchema } from './consts';
import { retrieveContext } from './bedrock-kb';

//SUPPORT - call to an agent

const supportToolSpec = {
    toolSpec: {
        name: "support",
        description: "Help with billing issues, charges and refunds. Connects to a human support agent",
        inputSchema: {
            json: DefaultToolSchema
        }
    }
}

function callSupport() {
    return {
        answer: "Let me get you an agent to help you ..."
    };
}

//KNOWLEDGE BASE - RAG tool
// Global RAG config that will be set by server.ts
let ragToolConfig: { enabled: boolean; kb_id?: string; kb_region?: string } = { enabled: false };

function setRagToolConfig(config: { enabled: boolean; kb_id?: string; kb_region?: string }) {
    ragToolConfig = config;
}

const knowledgeBaseToolSpec = {
    toolSpec: {
        name: "searchKnowledgeBase",
        description: "Search the company knowledge base for information about policies, procedures, FAQs, and documentation. Use this tool when the user asks questions that require specific company information.",
        inputSchema: {
            json: JSON.stringify({
                type: "object",
                properties: {
                    query: {
                        type: "string",
                        description: "The search query to find relevant information in the knowledge base"
                    }
                },
                required: ["query"]
            })
        }
    }
}

async function searchKnowledgeBase(args: { query: string }) {
    if (!ragToolConfig.enabled || !ragToolConfig.kb_id) {
        return {
            success: false,
            message: "Knowledge base is not configured for this call"
        };
    }

    try {
        const { contexts, retrieveTime } = await retrieveContext(
            args.query,
            {
                kb_id: ragToolConfig.kb_id,
                kb_region: ragToolConfig.kb_region || 'us-west-2',
                num_results: 3
            }
        );

        console.log(`[RAG Tool] Retrieved ${contexts.length} contexts in ${retrieveTime}ms for query: "${args.query}"`);

        if (contexts.length === 0) {
            return {
                success: false,
                message: "No relevant information found in the knowledge base"
            };
        }

        // Format contexts as a clear structured response
        const documents = contexts.map((ctx, idx) => ({
            content: ctx.text,
            relevance: ctx.score ? `${(ctx.score * 100).toFixed(1)}%` : 'N/A',
            source: ctx.source || 'Unknown'
        }));

        return {
            success: true,
            query: args.query,
            documentsFound: contexts.length,
            retrieveTimeMs: retrieveTime,
            documents
        };

    } catch (error) {
        console.error('[RAG Tool] Search failed:', error);
        return {
            success: false,
            message: `Knowledge base search failed: ${error}`
        };
    }
}

//GET date tool
const getDateToolSpec = {
    toolSpec: {
        name: "getDateTool",
        description: "get information about the current date",
        inputSchema: {
            json: DefaultToolSchema
        }
    }
}
function getDate() {
    const date = new Date().toLocaleString("en-US", { timeZone: "America/Los_Angeles" });
    const pstDate = new Date(date);
    return {
        date: pstDate.toISOString().split('T')[0],
        year: pstDate.getFullYear(),
        month: pstDate.getMonth() + 1,
        day: pstDate.getDate(),
        dayOfWeek: pstDate.toLocaleString('en-US', { weekday: 'long' }).toUpperCase(),
        timezone: "PST"
    };
}

//GET time tool
const getTimeToolSpec = {
    toolSpec: {
        name: "getTimeTool",
        description: "get information about the current time",
        inputSchema: {
            json: DefaultToolSchema
        }
    }
}
function getTime() {
    const pstTime = new Date().toLocaleString("en-US", { timeZone: "America/Los_Angeles" });
    return {
        timezone: "PST",
        formattedTime: new Date(pstTime).toLocaleTimeString('en-US', {
            hour12: true,
            hour: '2-digit',
            minute: '2-digit'
        })
    };
}

// Base tools that are always available
const baseTools = [
    getDateToolSpec,
    getTimeToolSpec,
    supportToolSpec,
]

// RAG tool that is only available when RAG is enabled
const ragTools = [
    knowledgeBaseToolSpec,
]

// Default: all tools available (for backward compatibility)
const availableTools = [
    ...baseTools,
    ...ragTools,
]

//all names are converted to lowercase
const toolHandlers: Record<string, Function> = {
    "support": callSupport,
    "getdatetool": getDate,
    "gettimetool": getTime,
    "searchknowledgebase": searchKnowledgeBase,
}


async function toolProcessor(toolName: string, toolArgs: string): Promise<Object> {

    console.log(toolArgs);
    const args = JSON.parse(toolArgs);
    console.log(`Tool ${toolName} invoked with args ${args}`);

    if (toolName in toolHandlers) {
        const tool: Function = toolHandlers[toolName];
        if (tool.constructor.name === "AsyncFunction") {
            return await toolHandlers[toolName](args);
        } else {
            return toolHandlers[toolName](args);
        }

    } else {
        console.log(`Tool ${toolName} not supported`);
        return {
            message: "I cannot help you with that request",
            success: false
        };
    }
}

export {
    availableTools,
    baseTools,
    ragTools,
    toolProcessor,
    setRagToolConfig
}
