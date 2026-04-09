import Fastify from 'fastify';
import fastifyFormBody from '@fastify/formbody';
import cors from '@fastify/cors';
import { randomUUID } from "node:crypto";
import { EventEmitter } from "node:events";
import { fromNodeProviderChain } from "@aws-sdk/credential-providers";
import { S2SBidirectionalStreamClient, StreamSession } from './nova-client';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, QueryCommand, GetCommand } from '@aws-sdk/lib-dynamodb';
import { CallRecordManager } from './call-records';
import { callLogger } from './call-logger';
import { AudioRecorder } from './audio-recorder';
import { setRagToolConfig, baseTools, ragTools } from './tools';
import { SipServer, type IncomingCallInfo } from './sip';
import { type RtpSession } from './sip';
// Farewell keywords that trigger automatic hangup
const FAREWELL_KEYWORDS = ['have a great day', 'que tenga buen día'];

const MAX_CALL_DURATION_MS = parseInt(process.env.MAX_CALL_DURATION_MS || '1200000', 10); // 20 minutes

//read the audio bytes from hello.pcm file
const helloAudioBytes = readFileSync(path.join(__dirname, '..', 'assets', 'hello.pcm'));

const sipEndpoint = process.env.SIP_ENDPOINT;

// SIP/RTP configuration for Chime Voice Connector
const PUBLIC_IP = process.env.PUBLIC_IP || '0.0.0.0';
const RTP_PORT_BASE = parseInt(process.env.RTP_PORT_BASE || '10000', 10);
const RTP_PORT_COUNT = parseInt(process.env.RTP_PORT_COUNT || '10000', 10);

// Initialize SIP server
const sipServer = new SipServer({
    publicIp: PUBLIC_IP,
    sipPort: 5060,
    rtpPortBase: RTP_PORT_BASE,
    rtpPortCount: RTP_PORT_COUNT,
});


const promptFile = path.join(__dirname, '..', 'system-prompt.md');
const SYSTEM_PROMPT = existsSync(promptFile)
    ? readFileSync(promptFile, 'utf-8').trim()
    : (process.env.SYSTEM_PROMPT || "You are a helpful assistant. Keep your responses short.");

// DynamoDB client for customer lookup
const ddbClient = DynamoDBDocumentClient.from(
    new DynamoDBClient({ region: process.env.DYNAMODB_REGION || 'us-west-2' })
);
const CUSTOMERS_TABLE = process.env.CUSTOMERS_TABLE || 'outbound-customers';
const PROMPTS_TABLE = process.env.PROMPTS_TABLE || 'outbound-prompts';

// Call records manager (DynamoDB)
const CALL_RECORDS_TABLE = process.env.CALL_RECORDS_TABLE || 'outbound-call-records';
const callRecords = new CallRecordManager(
    CALL_RECORDS_TABLE,
    process.env.DYNAMODB_REGION || 'us-west-2'
);

// In-memory active session tracking for SSE live transcript
interface ActiveSessionInfo {
    callSid: string;
    streamSid: string;
    customerPhone: string;
    customerName: string;
    voiceId: string;
    startTime: string;
    turnCount: number;
    emitter: EventEmitter;
}
const activeSessions = new Map<string, ActiveSessionInfo>();

async function lookupCustomerByPhone(phoneNumber: string): Promise<{
    customerName: string,
    voiceId?: string,
    promptId?: string,
    projectId?: string,
    notes?: string
} | null> {
    try {
        const result = await ddbClient.send(new QueryCommand({
            TableName: CUSTOMERS_TABLE,
            IndexName: 'phone-index',
            KeyConditionExpression: 'phone_number = :phone',
            ExpressionAttributeValues: { ':phone': phoneNumber },
            Limit: 1,
        }));

        if (result.Items && result.Items.length > 0) {
            const item = result.Items[0];
            console.log(`Customer found: ${item.customer_name}, voiceId: ${item.voice_id || 'default'}, promptId: ${item.prompt_id || 'default'}, projectId: ${item.project_id || 'none'}, notes: ${item.notes ? 'yes' : 'no'}`);
            return {
                customerName: item.customer_name,
                voiceId: item.voice_id,
                promptId: item.prompt_id,
                projectId: item.project_id,
                notes: item.notes || ''
            };
        }
        console.log(`No customer found for phone: ${phoneNumber}`);
        return null;
    } catch (error) {
        console.error('DynamoDB lookup error:', error);
        // Note: callSid not available at this point, can't log to call-specific logs
        return null;
    }
}

interface PromptConfig {
    prompt_content: string;
    rag_enabled?: boolean;
    kb_id?: string;
    kb_region?: string;
}

async function lookupPromptById(promptId: string): Promise<PromptConfig | null> {
    try {
        const result = await ddbClient.send(new GetCommand({
            TableName: PROMPTS_TABLE,
            Key: { prompt_id: promptId }
        }));

        if (result.Item) {
            console.log(`Prompt found: ${result.Item.prompt_name}, RAG: ${result.Item.rag_enabled ? 'enabled' : 'disabled'}`);
            return {
                prompt_content: result.Item.prompt_content,
                rag_enabled: result.Item.rag_enabled || false,
                kb_id: result.Item.kb_id || '',
                kb_region: result.Item.kb_region || 'us-west-2'
            };
        }
        console.log(`No prompt found for id: ${promptId}`);
        return null;
    } catch (error) {
        console.error('DynamoDB prompt lookup error:', error);
        return null;
    }
}

// Create the AWS Bedrock client (uses EC2 instance IAM role by default)
const bedrockClient = new S2SBidirectionalStreamClient({
    requestHandlerConfig: {
        maxConcurrentStreams: 10,
    },
    clientConfig: {
        region: process.env.AWS_REGION || "us-west-2",
        credentials: fromNodeProviderChain()
    }
});


// Initialize Fastify
const fastify = Fastify();

// Register CORS to allow frontend access
fastify.register(cors, {
    origin: '*',  // Allow all origins (adjust in production)
    methods: ['GET', 'POST', 'OPTIONS'],
});

fastify.register(fastifyFormBody);

// Root Route
fastify.get('/', async (request, reply) => {
    reply.send({ message: 'Voice Agent SIP Server is running!', activeCalls: sipServer.activeCallCount });
});


/**
 * SIP incoming call handler.
 * Replaces the Twilio WebSocket /media-stream handler.
 * Called when Voice Connector sends a SIP INVITE and the call is accepted.
 */
async function handleIncomingCall(call: IncomingCallInfo): Promise<void> {
    const { callId, callerPhone: customerPhone, rtpSession } = call;

    console.log(`[SIP Call] New call: ${callId}, from: ${customerPhone}`);

    // Create a Nova Sonic session
    const sessionId = randomUUID();
    const session: StreamSession = bedrockClient.createStreamSession(sessionId);
    bedrockClient.initiateSession(sessionId);

    // Use callId as the call identifier (replaces Twilio's callSid)
    const callSid = callId;
    session.streamSid = sessionId;

    let voiceId = process.env.VOICE_ID || 'tiffany';
    let enrichedPrompt = SYSTEM_PROMPT;
    let callTimer: ReturnType<typeof setTimeout> | null = null;
    let pendingHangup = false;
    let callEnded = false;
    let audioRecorder: AudioRecorder | null = null;
    let stopAcceptingUserAudio = false;
    let hangupTimerScheduled = false;

    // Conversation tracking for retry mechanism
    let conversationHistory: Array<{role: 'user' | 'assistant', text: string}> = [];
    let lastUserText = '';
    let lastAssistantText = '';
    let isGeneratingAudio = false;
    let lastGenerationStage = '';
    let retryCount = 0;
    const MAX_RETRIES = 2;

    // RAG configuration
    let ragConfig: { enabled: boolean; kb_id?: string; kb_region?: string } = { enabled: false };

    // Function to end the call via SIP BYE
    const endCall = async (reason: string) => {
        if (callEnded || !callSid) return;
        callEnded = true;
        console.log(`Ending call ${callSid}: ${reason}`);

        await callLogger.info(callSid, 'call-ended', `Call ended: ${reason}`, {
            reason,
            turnCount: activeSessions.get(callSid)?.turnCount || 0
        });

        try {
            sipServer.endCall(callSid);
            console.log(`Call ${callSid} ended successfully via SIP BYE`);
        } catch (error) {
            console.error(`Failed to end call ${callSid}:`, error);
            await callLogger.error(callSid, 'call-end-failed', `Failed to end call via SIP: ${error}`, {
                error: error instanceof Error ? error.message : String(error)
            });
        }
        if (callTimer) { clearTimeout(callTimer); callTimer = null; }

        // Finalize recording and upload to S3
        let recordingS3Key: string | undefined;
        if (audioRecorder) {
            try {
                const key = await audioRecorder.finalizeAndUpload();
                if (key) recordingS3Key = key;
            } catch (err) {
                console.error(`Failed to finalize recording for ${callSid}:`, err);
            }
        }

        callRecords.completeRecord(callSid, reason, recordingS3Key);
        const sess = activeSessions.get(callSid);
        if (sess) {
            sess.emitter.emit('done', { reason });
            activeSessions.delete(callSid);
        }
    };

    // Trigger hangup when farewell keyword detected
    const triggerHangup = (keyword: string) => {
        if (pendingHangup) return;
        console.log(`Farewell detected: "${keyword}" — scheduling hangup`);

        if (callSid) {
            callLogger.info(callSid, 'farewell-detected', `Farewell keyword detected: "${keyword}"`, {
                keyword,
                turnCount: activeSessions.get(callSid)?.turnCount || 0
            });
        }

        pendingHangup = true;
        stopAcceptingUserAudio = true;

        if (!isGeneratingAudio) {
            console.log('Audio already complete, scheduling hangup with 2s buffer');
            setTimeout(() => {
                if (!callEnded) endCall('Farewell hangup (post-audio)');
            }, 2000);
        }

        setTimeout(() => {
            if (pendingHangup && !callEnded) {
                endCall('Farewell hangup (fallback timer)');
            }
        }, 10000);
    };

    // --- Customer lookup and prompt setup (same as before) ---
    let customer = null;
    if (customerPhone) {
        customer = await lookupCustomerByPhone(customerPhone);
        if (customer) {
            voiceId = customer.voiceId || voiceId;

            let basePrompt = SYSTEM_PROMPT;
            let promptConfig: PromptConfig | null = null;

            if (customer.promptId) {
                promptConfig = await lookupPromptById(customer.promptId);
                if (promptConfig) {
                    basePrompt = promptConfig.prompt_content;
                    console.log(`Using custom prompt config: ${customer.promptId}, RAG: ${promptConfig.rag_enabled}`);

                    if (promptConfig.rag_enabled && promptConfig.kb_id) {
                        ragConfig = {
                            enabled: true,
                            kb_id: promptConfig.kb_id,
                            kb_region: promptConfig.kb_region || 'us-west-2'
                        };
                        setRagToolConfig(ragConfig);
                        console.log(`[RAG] RAG tool enabled for this call: KB=${ragConfig.kb_id}, Region=${ragConfig.kb_region}`);
                        basePrompt += '\n\n[CRITICAL INSTRUCTION - MANDATORY FOR EVERY TURN]\nRule: You MUST call the searchKnowledgeBase tool before answering EVERY single question from the user. This applies to EACH new question in the conversation, not just the first one.\n- First question: MUST call searchKnowledgeBase\n- Second question: MUST call searchKnowledgeBase again\n- Third question: MUST call searchKnowledgeBase again\n- Every subsequent question: MUST call searchKnowledgeBase again\nNEVER skip this step. NEVER reuse results from a previous search. Each new question requires a fresh search. If you answer without calling searchKnowledgeBase first, you are violating this instruction. If no relevant results are found, you may then use general knowledge. After receiving results, answer naturally without mentioning the tool or knowledge base.';
                    }
                }
            }

            enrichedPrompt = basePrompt
                .replace(/\{\{customer_name\}\}/g, customer.customerName)
                .replace(/\{\{notes\}\}/g, customer.notes || '');

            console.log(`Customer found: ${customer.customerName}, voiceId: ${voiceId}, using prompt: ${customer.promptId || 'default'}`);
        }
    }

    // Prepare tools list
    const sessionTools = ragConfig.enabled ? [...baseTools, ...ragTools] : baseTools;
    console.log(`Registering ${sessionTools.length} tools (RAG: ${ragConfig.enabled ? 'enabled' : 'disabled'})`);

    // Setup Nova Sonic session
    await session.setupPromptStart(voiceId, sessionTools);
    await session.setupSystemPrompt(undefined, enrichedPrompt);
    await session.setupStartAudio();

    audioRecorder = new AudioRecorder(callSid);

    // Start max call duration timer
    callTimer = setTimeout(async () => {
        console.log(`Max call duration (${MAX_CALL_DURATION_MS / 1000}s) reached`);
        await callLogger.warn(callSid, 'max-duration-reached', `Call exceeded max duration of ${MAX_CALL_DURATION_MS / 1000}s`, {
            maxDurationMs: MAX_CALL_DURATION_MS
        });
        endCall('max duration timeout');
    }, MAX_CALL_DURATION_MS);

    // Register active session for live transcript
    const customerName = customer?.customerName || '';
    const sessionInfo: ActiveSessionInfo = {
        callSid,
        streamSid: sessionId,
        customerPhone,
        customerName,
        voiceId,
        startTime: new Date().toISOString(),
        turnCount: 0,
        emitter: new EventEmitter(),
    };
    activeSessions.set(callSid, sessionInfo);

    callRecords.createRecord(callSid, sessionId, {
        customerPhone,
        customerName,
        voiceId,
        projectId: customer?.projectId,
    });

    await callLogger.info(callSid, 'call-started', `Call started from ${customerPhone}`, {
        customerName,
        voiceId,
        projectId: customer?.projectId,
    });

    // --- Bridge RTP audio to Nova Sonic ---
    // Inbound: RTP → PCM → Nova Sonic
    rtpSession.onAudioReceived((pcmBuffer: Buffer) => {
        if (pendingHangup || callEnded || stopAcceptingUserAudio) return;
        if (audioRecorder) audioRecorder.appendCustomerAudio(pcmBuffer);
        currentSession.streamAudio(pcmBuffer);
    });

    // Track current session (may change on retry)
    let lastContentType = '';
    let currentSession = session;

    // Retry function for recovering from Bedrock errors
    const retrySession = async () => {
        if (callEnded) return false;
        if (retryCount >= MAX_RETRIES) {
            console.log(`Max retries (${MAX_RETRIES}) reached, giving up`);
            return false;
        }
        if (!isGeneratingAudio || !lastAssistantText) {
            console.log('Not retrying: not in audio generation phase or no text to retry');
            return false;
        }

        retryCount++;
        console.log(`Attempting retry ${retryCount}/${MAX_RETRIES}...`);

        try {
            const newSessionId = randomUUID();
            const newSession: StreamSession = bedrockClient.createStreamSession(newSessionId);

            let historyText = '';
            if (conversationHistory.length > 0) {
                historyText = '\n\nPREVIOUS CONVERSATION:\n';
                conversationHistory.forEach(turn => {
                    const label = turn.role === 'user' ? 'Customer' : 'Assistant';
                    historyText += `${label}: ${turn.text}\n`;
                });
            }

            const retryPrompt = enrichedPrompt + historyText + `\n\nIMPORTANT: You were just saying: "${lastAssistantText}". Continue from where you left off naturally.`;
            newSession.streamSid = currentSession.streamSid;

            const retrySessionTools = ragConfig.enabled ? [...baseTools, ...ragTools] : baseTools;
            await newSession.setupPromptStart(voiceId, retrySessionTools);
            await newSession.setupSystemPrompt(undefined, retryPrompt);
            await newSession.setupStartAudio();

            setupSessionHandlers(newSession);
            currentSession = newSession;

            bedrockClient.initiateSession(newSessionId).catch(err =>
                console.error('Retry session stream error:', err)
            );

            await new Promise(resolve => setTimeout(resolve, 100));
            await newSession.streamAudio(helloAudioBytes);

            isGeneratingAudio = false;
            pendingHangup = false;
            stopAcceptingUserAudio = false;
            hangupTimerScheduled = false;

            console.log('Session retry successful');
            return true;
        } catch (error) {
            console.error('Failed to retry session:', error);
            return false;
        }
    };

    // Helper function to setup all Nova Sonic event handlers
    const setupSessionHandlers = (sess: StreamSession) => {
        sess.onEvent('contentStart', (data) => {
            lastContentType = data.type || '';
            if (data.additionalModelFields) {
                try {
                    const additional = typeof data.additionalModelFields === 'string'
                        ? JSON.parse(data.additionalModelFields) : data.additionalModelFields;
                    lastGenerationStage = additional.generationStage || '';
                } catch { lastGenerationStage = ''; }
            } else {
                lastGenerationStage = '';
            }
            if (data.type === 'AUDIO' && data.role === 'ASSISTANT') {
                isGeneratingAudio = true;
            }
            console.log(`contentStart: type=${data.type}, role=${data.role || ''}, stage=${lastGenerationStage}`);
        });

        sess.onEvent('textOutput', async (data) => {
            if (lastGenerationStage === 'SPECULATIVE') return;
            const role = data.role?.toLowerCase();
            const content = data.content || '';
            console.log(`[${role?.toUpperCase()}] ${content}`);

            if (role === 'user') {
                lastUserText = content;
            } else if (role === 'assistant') {
                lastAssistantText = content;
                const lower = content.toLowerCase();
                for (const kw of FAREWELL_KEYWORDS) {
                    if (lower.includes(kw)) {
                        triggerHangup(kw);
                        break;
                    }
                }
            }

            if (callSid && (role === 'user' || role === 'assistant')) {
                const sessInfo = activeSessions.get(callSid);
                if (sessInfo) {
                    sessInfo.emitter.emit('text', { role, text: content });
                }
            }
        });

        // Outbound: Nova Sonic → PCM → RTP
        sess.onEvent('audioOutput', (data) => {
            if (!data['content']) return;
            const buffer = Buffer.from(data['content'], 'base64');

            if (audioRecorder) audioRecorder.appendAiAudio(buffer);

            // Send PCM directly to RTP session (it handles PCM→mulaw conversion and RTP packaging)
            rtpSession.sendAudio(buffer);
        });

        sess.onEvent('contentEnd', async (data) => {
            console.log(`contentEnd: type=${lastContentType}, stage=${lastGenerationStage}, stopReason=${data["stopReason"] || 'none'}`);

            if (lastContentType === 'TEXT') {
                if (lastGenerationStage === 'FINAL') {
                    if (lastUserText) {
                        conversationHistory.push({ role: 'user', text: lastUserText });
                        if (callSid) {
                            callRecords.appendTranscript(callSid, { role: 'user', text: lastUserText });
                            const sessInfo = activeSessions.get(callSid);
                            if (sessInfo) sessInfo.turnCount++;
                            await callLogger.debug(callSid, 'user-utterance', `User said: ${lastUserText.substring(0, 100)}`, {
                                textLength: lastUserText.length,
                                turnCount: sessInfo?.turnCount || 0,
                            });
                        }
                        lastUserText = '';
                    }
                    if (lastAssistantText) {
                        conversationHistory.push({ role: 'assistant', text: lastAssistantText });
                        if (callSid) {
                            callRecords.appendTranscript(callSid, { role: 'assistant', text: lastAssistantText });
                            const sessInfo = activeSessions.get(callSid);
                            if (sessInfo) sessInfo.turnCount++;
                            await callLogger.debug(callSid, 'assistant-response', `Assistant said: ${lastAssistantText.substring(0, 100)}`, {
                                textLength: lastAssistantText.length,
                                turnCount: sessInfo?.turnCount || 0,
                            });
                        }
                        lastAssistantText = '';
                    }
                }
            } else if (lastContentType === 'AUDIO') {
                isGeneratingAudio = false;
                lastAssistantText = '';
            }

            if (pendingHangup && lastContentType === 'AUDIO' && !hangupTimerScheduled) {
                hangupTimerScheduled = true;
                console.log('Audio complete during hangup, waiting 2s buffer...');
                setTimeout(() => {
                    endCall('AI hangup (after audio complete + buffer)');
                }, 2000);
            }
        });

        sess.onEvent('toolUse', async (data) => {
            console.log('Tool use detected:', data.toolName);

            // Handle support tool: end current call (SIP transfer not yet implemented)
            if (data.toolName == 'support') {
                console.log(`Support requested for call ${callSid}`);
                if (sipEndpoint) {
                    // TODO: Implement SIP REFER for call transfer
                    console.log(`Call transfer to ${sipEndpoint} not yet implemented, ending call`);
                }
                endCall('transfer_requested');
            }

            if (data.toolName?.toLowerCase() === 'searchknowledgebase') {
                const query = data.content ? JSON.parse(data.content).query : 'unknown';
                console.log(`[RAG Tool] Nova is searching knowledge base for: "${query}"`);
                callLogger.info(callSid, 'rag-tool-called', `Nova called searchKnowledgeBase`, {
                    query,
                    toolUseId: data.toolUseId
                }).catch(err => console.error('Failed to log RAG tool call:', err));
            }
        });

        sess.onEvent('toolResult', (data) => {
            console.log('Tool result received:', data.toolUseId);
            if (data.result) {
                try {
                    const result = typeof data.result === 'string' ? JSON.parse(data.result) : data.result;
                    if (result.documentsFound !== undefined) {
                        console.log(`[RAG Tool] Retrieved ${result.documentsFound} documents in ${result.retrieveTimeMs}ms`);
                        if (result.success && result.documents) {
                            const retrievedDocs = result.documents.map((doc: any, idx: number) => ({
                                index: idx + 1, relevance: doc.relevance,
                                preview: doc.content.substring(0, 150) + (doc.content.length > 150 ? '...' : ''),
                                source: doc.source
                            }));
                            callLogger.info(callSid, 'rag-tool-success', `RAG search successful`, {
                                query: result.query, retrieveTime: `${result.retrieveTimeMs}ms`,
                                documentsFound: result.documentsFound, documents: retrievedDocs
                            }).catch(err => console.error('Failed to log RAG tool success:', err));
                        } else {
                            callLogger.warn(callSid, 'rag-tool-no-results', `RAG search returned no results`, {
                                query: result.query, message: result.message
                            }).catch(err => console.error('Failed to log RAG no results:', err));
                        }
                    }
                } catch (err) {
                    console.error('[RAG Tool] Failed to parse tool result:', err);
                }
            }
        });

        sess.onEvent('streamComplete', () => {
            console.log('Stream completed for session:', sess.streamSid);
        });

        sess.onEvent('error', async (data) => {
            console.error('Error in session:', data);
            const errorDetails = data.details || '';
            const isModelStreamError = errorDetails.includes('ModelStreamErrorException') ||
                                      errorDetails.includes('encountered an unexpected error');

            if (isModelStreamError) {
                console.log('Detected ModelStreamErrorException, attempting retry...');
                if (callSid) {
                    await callLogger.warn(callSid, 'model-stream-error', 'ModelStreamErrorException occurred, retrying session', {
                        errorDetails, retryCount
                    });
                }
                const retried = await retrySession();
                if (!retried) {
                    console.error('Retry failed or not applicable');
                    if (callSid) {
                        await callLogger.error(callSid, 'retry-failed', 'Session retry failed', {
                            errorDetails, retryCount
                        });
                    }
                }
            } else {
                console.error('Non-retryable error:', errorDetails);
                if (callSid) {
                    await callLogger.error(callSid, 'non-retryable-error', 'Non-retryable error occurred', { errorDetails });
                }
            }
        });
    };

    // Initialize event handlers for the first session
    setupSessionHandlers(session);

    // Send hello audio to trigger AI to speak first
    await session.streamAudio(helloAudioBytes);

    console.log(`[SIP Call] Call ${callSid} fully initialized, RTP bridging active`);
}

// Register SIP incoming call handler
sipServer.onIncomingCall((call) => {
    handleIncomingCall(call).catch(err => {
        console.error(`[SIP Call] Error handling call ${call.callId}:`, err);
        sipServer.endCall(call.callId);
    });
});

// Handle remote hangup (BYE from Voice Connector)
sipServer.onCallEnded(async (callId, reason) => {
    console.log(`[SIP] Remote hangup: ${callId}, reason: ${reason}`);
    const sessInfo = activeSessions.get(callId);
    if (sessInfo) {
        callLogger.warn(callId, 'remote-hangup', `Remote party hung up: ${reason}`, {
            turnCount: sessInfo.turnCount
        });
        callRecords.completeRecord(callId, reason);
        sessInfo.emitter.emit('done', { reason });
        activeSessions.delete(callId);
    }
});


// === Monitoring API endpoints ===

// GET /api/active-calls — return list of active calls on this instance
fastify.get('/api/active-calls', async (_request, reply) => {
    const calls = Array.from(activeSessions.values()).map((s) => ({
        callSid: s.callSid,
        streamSid: s.streamSid,
        customerPhone: s.customerPhone,
        customerName: s.customerName,
        voiceId: s.voiceId,
        startTime: s.startTime,
        turnCount: s.turnCount,
    }));
    reply.send({ activeCalls: calls, totalActive: calls.length });
});

// GET /api/live-transcript/:callSid — SSE stream of live transcript
fastify.get('/api/live-transcript/:callSid', async (request, reply) => {
    const { callSid } = request.params as { callSid: string };
    const sessInfo = activeSessions.get(callSid);

    if (!sessInfo) {
        reply.code(404).send({ error: 'Call not found or already ended' });
        return;
    }

    // SSE headers
    reply.raw.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
    });

    const sendEvent = (eventType: string, data: unknown) => {
        reply.raw.write(`event: ${eventType}\ndata: ${JSON.stringify(data)}\n\n`);
    };

    // Send initial status
    sendEvent('status', {
        callSid: sessInfo.callSid,
        customerPhone: sessInfo.customerPhone,
        customerName: sessInfo.customerName,
        startTime: sessInfo.startTime,
        turnCount: sessInfo.turnCount,
    });

    const onText = (data: { role: string; text: string }) => {
        sendEvent('text', {
            type: 'text',
            role: data.role,
            text: data.text,
            timestamp: new Date().toISOString(),
        });
    };

    const onDone = (data: { reason: string }) => {
        sendEvent('done', { type: 'done', reason: data.reason });
        reply.raw.end();
    };

    sessInfo.emitter.on('text', onText);
    sessInfo.emitter.on('done', onDone);

    // Clean up on client disconnect
    request.raw.on('close', () => {
        sessInfo.emitter.off('text', onText);
        sessInfo.emitter.off('done', onDone);
    });
});

const PORT = parseInt(process.env.PORT || '3000', 10);

// Start both Fastify (HTTP) and SIP server
async function startServers() {
    try {
        // Start SIP server (UDP 5060)
        await sipServer.start();
        console.log(`SIP server started on UDP 5060, PUBLIC_IP: ${PUBLIC_IP}`);

        // Start Fastify (HTTP for REST API, SSE)
        await fastify.listen({ host: '0.0.0.0', port: PORT });
        console.log(`HTTP server listening on port ${PORT}`);
        console.log(`RTP port range: ${RTP_PORT_BASE}-${RTP_PORT_BASE + RTP_PORT_COUNT}`);
    } catch (err) {
        console.error('Failed to start servers:', err);
        process.exit(1);
    }
}

startServers();

// Graceful shutdown on SIGTERM (sent by ECS when stopping tasks)
process.on('SIGTERM', async () => {
    console.log('SIGTERM received, shutting down gracefully...');
    sipServer.stop();
    await fastify.close();
    process.exit(0);
});
