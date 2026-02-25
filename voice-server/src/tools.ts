import { DefaultToolSchema } from './consts';

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

const availableTools = [
    getDateToolSpec,
    getTimeToolSpec,
    supportToolSpec,
]

//all names are converted to lowercase
const toolHandlers: Record<string, Function> = {
    "support": callSupport,
    "getdatetool": getDate,
    "gettimetool": getTime,
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
    toolProcessor
}
