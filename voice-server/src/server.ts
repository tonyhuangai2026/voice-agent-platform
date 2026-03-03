import Fastify from 'fastify';
import fastifyFormBody from '@fastify/formbody';
import fastifyWs from '@fastify/websocket';
import cors from '@fastify/cors';
import { randomUUID } from "node:crypto";
import { EventEmitter } from "node:events";
import { fromNodeProviderChain } from "@aws-sdk/credential-providers";
import { S2SBidirectionalStreamClient, StreamSession } from './nova-client';
import {mulaw} from 'alawmulaw';
import { Twilio } from "twilio"
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, QueryCommand, GetCommand } from '@aws-sdk/lib-dynamodb';
import { CallRecordManager } from './call-records';
import { callLogger } from './call-logger';
import { AudioRecorder } from './audio-recorder';
import { setRagToolConfig, baseTools, ragTools } from './tools';
// Farewell keywords that trigger automatic hangup
const FAREWELL_KEYWORDS = ['have a great day', 'que tenga buen día'];

const MAX_CALL_DURATION_MS = parseInt(process.env.MAX_CALL_DURATION_MS || '1200000', 10); // 20 minutes

//read the audio bytes from hello.pcm file
const helloAudioBytes = readFileSync(path.join(__dirname, '..', 'assets', 'hello.pcm'));

const apiSid = process.env.TWILIO_API_SID;
const apiSecret = process.env.TWILIO_API_SECRET;
const accountSid = process.env.TWILIO_ACCOUNT_SID;
const sipEndpoint = process.env.SIP_ENDPOINT;

const fromNumber = process.env.TWILIO_FROM_NUMBER;
const toNumber = process.env.TWILIO_VERIFIED_CALLER_ID;

const twClient = new Twilio(apiSid, apiSecret, {accountSid});


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


const sipTwiml = `
<Response>
    <Say>Hang on for a moment while I forward the call to an agent</Say>
    <Pause length="1"/>
    <Dial>
    <Sip>${sipEndpoint}</Sip>
</Dial>
</Response>
`;

// Initialize Fastify
const fastify = Fastify();

// Register CORS to allow frontend access
fastify.register(cors, {
    origin: '*',  // Allow all origins (adjust in production)
    methods: ['GET', 'POST', 'OPTIONS'],
});

fastify.register(fastifyFormBody);
fastify.register(fastifyWs);

// Root Route
fastify.get('/', async (request, reply) => {
    reply.send({ message: 'Twilio Media Stream Server is running!' });
});


// Route to initiate outbound calls to a phone number from Twilio
// Invoke this endpoint to initiate an outbound call
fastify.all('/outbound-call', async (request, reply) => {

    const twimlResponse = `<?xml version="1.0" encoding="UTF-8"?>
                          <Response>
                              <Connect>
                                <Stream url="wss://${request.headers.host}/media-stream" />
                              </Connect>
                          </Response>`;


    const call = await twClient.calls.create({
        from: fromNumber,
        to: toNumber,
        twiml: twimlResponse,
      });

      reply.type('text/plain').send("Ok");

});


// Route for Twilio to handle incoming and outgoing calls
fastify.all('/incoming-call', async (request, reply) => {
    // Extract the customer's phone number and voiceId from Twilio webhook params
    const params = (request.body || request.query || {}) as Record<string, string>;
    const customerPhone = params.From || params.To || '';
    const voiceId = params.voiceId || 'tiffany'; // Default to 'tiffany' if not provided
    console.log(`Incoming call, customer phone: ${customerPhone}, voiceId: ${voiceId}`);

    const twimlResponse = `<?xml version="1.0" encoding="UTF-8"?>
                          <Response>
                              <Connect>
                                <Stream url="wss://${request.headers.host}/media-stream">
                                  <Parameter name="customerPhone" value="${customerPhone}" />
                                  <Parameter name="voiceId" value="${voiceId}" />
                                </Stream>
                              </Connect>
                          </Response>`;
    reply.type('text/xml').send(twimlResponse);
});


// Route for Twilio to handle incoming and outgoing calls
fastify.all('/failover', async (request, reply) => {

    reply.type('text/xml').send(sipTwiml);
});


// WebSocket route for media-stream
fastify.register(async (fastify) => {
    fastify.get('/media-stream', { websocket: true }, (connection, req) => {
        console.log('Client connected');

        //create a session
        const sessionId = randomUUID();
        const session: StreamSession = bedrockClient.createStreamSession(sessionId);
        bedrockClient.initiateSession(sessionId) //initiate the session

        let callSid = '';
        let customerPhone = '';
        let voiceId = 'tiffany'; // Default voice, will be updated from TwiML params
        let enrichedPrompt = SYSTEM_PROMPT; // will be updated with customer info
        let callTimer: ReturnType<typeof setTimeout> | null = null;
        let pendingHangup = false; // flag: AI requested hangup, waiting for audio to finish
        let callEnded = false; // prevent double hangup
        let audioRecorder: AudioRecorder | null = null;
        let stopAcceptingUserAudio = false; // stop accepting user audio after hangup requested
        let hangupTimerScheduled = false; // prevent multiple 2s hangup timers

        // Conversation tracking for retry mechanism
        let conversationHistory: Array<{role: 'user' | 'assistant', text: string}> = [];
        let lastUserText = '';
        let lastAssistantText = '';
        let isGeneratingAudio = false;
        let lastGenerationStage = '';
        let retryCount = 0;
        const MAX_RETRIES = 2;

        // RAG configuration (loaded during call start)
        let ragConfig: { enabled: boolean; kb_id?: string; kb_region?: string } = { enabled: false };

        // Function to end the call via Twilio API
        const endCall = async (reason: string) => {
            if (callEnded || !callSid) return;
            callEnded = true;
            console.log(`Ending call ${callSid}: ${reason}`);

            // Log call end
            await callLogger.info(callSid, 'call-ended', `Call ended: ${reason}`, {
                reason,
                turnCount: activeSessions.get(callSid)?.turnCount || 0
            });

            try {
                await twClient.calls(callSid).update({ status: 'completed' });
                console.log(`Call ${callSid} ended successfully`);
            } catch (error) {
                console.error(`Failed to end call ${callSid}:`, error);
                await callLogger.error(callSid, 'call-end-failed', `Failed to end call via Twilio API: ${error}`, {
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

            // Complete the call record and notify SSE listeners
            callRecords.completeRecord(callSid, reason, recordingS3Key);
            const sess = activeSessions.get(callSid);
            if (sess) {
                sess.emitter.emit('done', { reason });
                activeSessions.delete(callSid);
            }
        };

        // Trigger hangup when farewell keyword detected in AI's speech
        const triggerHangup = (keyword: string) => {
            if (pendingHangup) return; // already triggered
            console.log(`Farewell detected: "${keyword}" — scheduling hangup`);

            // Log farewell detection
            if (callSid) {
                callLogger.info(callSid, 'farewell-detected', `Farewell keyword detected: "${keyword}"`, {
                    keyword,
                    turnCount: activeSessions.get(callSid)?.turnCount || 0
                });
            }

            pendingHangup = true;
            stopAcceptingUserAudio = true;

            if (!isGeneratingAudio) {
                // Audio already finished playing, schedule immediate hangup with 2s buffer
                console.log('Audio already complete, scheduling hangup with 2s buffer');
                setTimeout(() => {
                    if (!callEnded) endCall('Farewell hangup (post-audio)');
                }, 2000);
            }
            // If audio is still generating, contentEnd handler will schedule 2s hangup

            // Fallback: if nothing triggers within 10s, hang up anyway
            setTimeout(() => {
                if (pendingHangup && !callEnded) {
                    endCall('Farewell hangup (fallback timer)');
                }
            }, 10000);
        };

        // Handle incoming messages from Twilio
        connection.on('message', async (message) => {

            try {
                const data = JSON.parse(message);
                //use streamSid as session id. little complicated in conference scenarios


                switch (data.event) {
                    case 'connected':
                        console.log(`connected event ${message}`);
                        // Don't setup prompt start here - wait for 'start' event to get voiceId parameter
                        break;
                    case 'start':
                        // Extract callSid early for logging
                        callSid = data.start.callSid;
                        session.streamSid = data.streamSid;

                        // Extract customer phone from Twilio custom parameters
                        customerPhone = data.start?.customParameters?.customerPhone || '';
                        console.log(`Stream start, callSid: ${callSid}, customerPhone: ${customerPhone}`);

                        // Look up customer info in DynamoDB (including voice_id and prompt_id)
                        let customer = null;
                        if (customerPhone) {
                            customer = await lookupCustomerByPhone(customerPhone);
                            if (customer) {
                                // Use customer's voice_id if available, otherwise fallback to TwiML param or default
                                voiceId = customer.voiceId || data.start?.customParameters?.voiceId || 'tiffany';

                                // Look up prompt configuration if customer has prompt_id
                                let basePrompt = SYSTEM_PROMPT;
                                let promptConfig: PromptConfig | null = null;

                                if (customer.promptId) {
                                    promptConfig = await lookupPromptById(customer.promptId);
                                    if (promptConfig) {
                                        basePrompt = promptConfig.prompt_content;
                                        console.log(`Using custom prompt config: ${customer.promptId}, RAG: ${promptConfig.rag_enabled}`);

                                        // Configure RAG tool if enabled
                                        if (promptConfig.rag_enabled && promptConfig.kb_id) {
                                            ragConfig = {
                                                enabled: true,
                                                kb_id: promptConfig.kb_id,
                                                kb_region: promptConfig.kb_region || 'us-west-2'
                                            };

                                            // Set global RAG config for the tool
                                            setRagToolConfig(ragConfig);

                                            console.log(`[RAG] RAG tool enabled for this call: KB=${ragConfig.kb_id}, Region=${ragConfig.kb_region}`);

                                            // Add tool usage instruction to base prompt
                                            basePrompt += '\n\n[CRITICAL INSTRUCTION] You MUST use the searchKnowledgeBase tool whenever the user asks about:\n- Company policies (leave, overtime, reimbursement, etc.)\n- Working hours, schedules, or attendance\n- HR processes (onboarding, resignation, performance reviews)\n- IT support, equipment, or account requests\n- Office facilities or procedures\n- Training or benefits\n- ANY company-specific information\n\nDo NOT answer these questions from general knowledge - you MUST call searchKnowledgeBase first to get accurate, company-specific information. After receiving results, answer naturally without mentioning the tool or knowledge base.';
                                        }
                                    }
                                }

                                // Use the prompt directly without hardcoded context
                                // Prompt templates should handle their own variable substitution
                                enrichedPrompt = basePrompt
                                    .replace(/\{\{customer_name\}\}/g, customer.customerName)
                                    .replace(/\{\{notes\}\}/g, customer.notes || '');

                                console.log(`Customer found: ${customer.customerName}, voiceId: ${voiceId}, using prompt: ${customer.promptId || 'default'}`);

                                // Debug: Log if RAG instruction was added
                                if (ragConfig.enabled) {
                                    console.log(`[RAG] System prompt includes RAG instruction: ${enrichedPrompt.includes('searchKnowledgeBase')}`);
                                    console.log(`[RAG] System prompt length: ${enrichedPrompt.length} chars, last 200: ${enrichedPrompt.substring(enrichedPrompt.length - 200)}`);
                                }
                            }
                        }

                        console.log(`Final voiceId: ${voiceId}`);

                        // Prepare tools list based on RAG configuration
                        const sessionTools = ragConfig.enabled
                            ? [...baseTools, ...ragTools]  // Include RAG tool when enabled
                            : baseTools;  // Only base tools when RAG disabled

                        console.log(`Registering ${sessionTools.length} tools (RAG: ${ragConfig.enabled ? 'enabled' : 'disabled'})`);

                        // Setup prompt start with voiceId and custom tools FIRST (critical for Nova session)
                        await session.setupPromptStart(voiceId, sessionTools);
                        await session.setupSystemPrompt(undefined, enrichedPrompt);
                        await session.setupStartAudio();

                        // callSid and streamSid already assigned earlier
                        audioRecorder = new AudioRecorder(callSid);
                        console.log(`Stream started streamSid: ${session.streamSid}, callSid: ${callSid}`);

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
                            streamSid: session.streamSid,
                            customerPhone,
                            customerName,
                            voiceId,
                            startTime: new Date().toISOString(),
                            turnCount: 0,
                            emitter: new EventEmitter(),
                        };
                        activeSessions.set(callSid, sessionInfo);

                        // Write to DynamoDB (include projectId from customer lookup)
                        callRecords.createRecord(callSid, session.streamSid, {
                            customerPhone,
                            customerName,
                            voiceId,
                            projectId: customer?.projectId,
                        });

                        // Log call started
                        await callLogger.info(callSid, 'call-started', `Call started from ${customerPhone}`, {
                            customerName,
                            voiceId,
                            projectId: customer?.projectId,
                        });

                        //send the audio bytes that say "hello" as to mimick the user greeting to allow model to speak first
                        await session.streamAudio(helloAudioBytes);
                        break;

                    case 'media':

                        if (!(currentSession.streamSid)) break;

                        // If hangup is pending, call ended, or stop accepting audio, ignore new user audio
                        if (pendingHangup || callEnded || stopAcceptingUserAudio) {
                            break;
                        }

                        //convert from 8-bit mulaw to 16-bit LPCM
                        const audioInput = Buffer.from(data.media.payload, 'base64');
                        const pcmSamples = mulaw.decode(audioInput);
                        const audioBuffer = Buffer.from(pcmSamples.buffer);

                        if (audioRecorder) audioRecorder.appendCustomerAudio(audioBuffer);

                        await currentSession.streamAudio(audioBuffer);
                        break;

                    default:
                        console.log('Received non-media event:', data.event);
                        break;
                }
            } catch (error) {
                console.error('Error parsing message:', error, 'Message:', message);

                // Log message parsing error
                if (callSid) {
                    await callLogger.error(callSid, 'message-parse-error', 'Failed to parse WebSocket message', {
                        error: error instanceof Error ? error.message : String(error),
                        messagePreview: message.toString().substring(0, 100)
                    });
                }

                connection.close();
            }
        });

        // Handle connection close
        connection.on('close', async () => {
            console.log('Client disconnected.');
            if (callTimer) { clearTimeout(callTimer); callTimer = null; }

            // If call wasn't already ended, mark as disconnect
            if (!callEnded && callSid) {
                // Log unexpected disconnection
                callLogger.warn(callSid, 'unexpected-disconnect', 'WebSocket connection closed before call ended', {
                    turnCount: activeSessions.get(callSid)?.turnCount || 0
                });

                // Finalize recording on disconnect
                let recordingS3Key: string | undefined;
                if (audioRecorder) {
                    try {
                        const key = await audioRecorder.finalizeAndUpload();
                        if (key) recordingS3Key = key;
                    } catch (err) {
                        console.error(`Failed to finalize recording on disconnect for ${callSid}:`, err);
                    }
                }

                callRecords.completeRecord(callSid, 'disconnect', recordingS3Key);
                const sess = activeSessions.get(callSid);
                if (sess) {
                    sess.emitter.emit('done', { reason: 'disconnect' });
                    activeSessions.delete(callSid);
                }
            }
        });


        /**
         * Handle all the Nova Sonic events
         */

        // Track the type of the current content block (TEXT, AUDIO, TOOL)
        let lastContentType = '';
        let currentSession = session; // Track current active session (may change on retry)

        // Retry function for recovering from Bedrock errors
        const retrySession = async () => {
            if (callEnded) return false;

            // Check if we should retry
            if (retryCount >= MAX_RETRIES) {
                console.log(`Max retries (${MAX_RETRIES}) reached, giving up`);
                return false;
            }

            // Only retry if error occurred during audio generation and we have the text
            if (!isGeneratingAudio || !lastAssistantText) {
                console.log('Not retrying: not in audio generation phase or no text to retry');
                return false;
            }

            retryCount++;
            console.log(`Attempting retry ${retryCount}/${MAX_RETRIES}...`);
            console.log(`Retrying with text: "${lastAssistantText.substring(0, 100)}..."`);
            console.log(`Conversation history length: ${conversationHistory.length}`);

            try {
                // Create a new session
                const newSessionId = randomUUID();
                const newSession: StreamSession = bedrockClient.createStreamSession(newSessionId);

                // Build conversation history for system prompt
                let historyText = '';
                if (conversationHistory.length > 0) {
                    historyText = '\n\nPREVIOUS CONVERSATION:\n';
                    conversationHistory.forEach(turn => {
                        const label = turn.role === 'user' ? 'Customer' : 'Assistant';
                        historyText += `${label}: ${turn.text}\n`;
                    });
                    console.log(`Conversation history:\n${historyText}`);
                } else {
                    console.log('No conversation history found');
                }

                const retryPrompt = enrichedPrompt + historyText + `\n\nIMPORTANT: You were just saying: "${lastAssistantText}". Continue from where you left off naturally.`;
                console.log(`Retry prompt length: ${retryPrompt.length} characters`);

                // Preserve streamSid from old session (needed for Twilio WebSocket)
                newSession.streamSid = currentSession.streamSid;

                // IMPORTANT: Setup session events in the correct order
                // 1. First add SessionStart by calling a setup method (if available)
                // 2. Then add other events in order

                // Prepare tools list based on RAG configuration (same as initial session)
                const retrySessionTools = ragConfig.enabled
                    ? [...baseTools, ...ragTools]
                    : baseTools;

                // Setup new session with conversation history
                // Note: These will be queued, and SessionStart will be prepended by initiateSession
                await newSession.setupPromptStart(voiceId, retrySessionTools);
                await newSession.setupSystemPrompt(undefined, retryPrompt);
                await newSession.setupStartAudio();

                // Copy event handlers to new session
                setupSessionHandlers(newSession);

                // Update current session reference
                currentSession = newSession;

                // Initiate the new session - fire-and-forget (don't await, it blocks until stream ends)
                bedrockClient.initiateSession(newSessionId).catch(err =>
                    console.error('Retry session stream error:', err)
                );

                // Short wait to ensure stream is established
                await new Promise(resolve => setTimeout(resolve, 100));

                // Send hello audio to trigger AI to speak (system prompt has "You were just saying: ..." context)
                await newSession.streamAudio(helloAudioBytes);

                // Reset retry state
                isGeneratingAudio = false;
                pendingHangup = false;
                stopAcceptingUserAudio = false;
                hangupTimerScheduled = false;

                console.log('Session retry successful, new session created with preserved streamSid');
                return true;

            } catch (error) {
                console.error('Failed to retry session:', error);
                return false;
            }
        };

        // Helper function to setup all event handlers (to reuse on retry)
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
                    // RAG is now handled via tool calls - Nova will call searchKnowledgeBase tool when needed
                }
                else if (role === 'assistant') {
                    lastAssistantText = content;
                    // Check for farewell keywords to trigger hangup
                    const lower = content.toLowerCase();
                    for (const kw of FAREWELL_KEYWORDS) {
                        if (lower.includes(kw)) {
                            triggerHangup(kw);
                            break;
                        }
                    }
                }

                // Emit live transcript event for SSE subscribers
                if (callSid && (role === 'user' || role === 'assistant')) {
                    const sessInfo = activeSessions.get(callSid);
                    if (sessInfo) {
                        sessInfo.emitter.emit('text', { role, text: content });
                    }
                }
            });

            sess.onEvent('audioOutput', (data) => {
                const contentLen = data['content']?.length || 0;
                console.log(`[audioOutput] streamSid=${sess.streamSid}, contentLen=${contentLen}, wsReady=${connection.readyState}`);
                if (!data['content']) {
                    console.warn('[audioOutput] No content in audio data!');
                    return;
                }
                const buffer = Buffer.from(data['content'], 'base64');

                if (audioRecorder) audioRecorder.appendAiAudio(buffer);

                const pcmSamples = new Int16Array(buffer.buffer, buffer.byteOffset, buffer.length / Int16Array.BYTES_PER_ELEMENT);
                const mulawSamples = mulaw.encode(pcmSamples);
                const payload = Buffer.from(mulawSamples).toString('base64');
                const audioResponse = {
                    event: "media",
                    media: {
                        track: "outbound",
                        payload
                    },
                    "streamSid": sess.streamSid
                };
                connection.send(JSON.stringify(audioResponse));
            });

            sess.onEvent('contentEnd', async (data) => {
                console.log(`contentEnd: type=${lastContentType}, stage=${lastGenerationStage}, stopReason=${data["stopReason"] || 'none'}`);
                if (data["stopReason"] == "INTERRUPTED") {
                    const clearMessage = {
                        "event": "clear",
                        "streamSid": sess.streamSid
                    }
                    connection.send(JSON.stringify(clearMessage));
                }

                if (lastContentType === 'TEXT') {
                    // Only save FINAL stage content (not SPECULATIVE)
                    if (lastGenerationStage === 'FINAL') {
                        if (lastUserText) {
                            conversationHistory.push({ role: 'user', text: lastUserText });
                            console.log(`History saved [USER]: ${lastUserText.substring(0, 80)}${lastUserText.length > 80 ? '...' : ''} (total: ${conversationHistory.length})`);
                            // Append to DynamoDB call record
                            if (callSid) {
                                callRecords.appendTranscript(callSid, { role: 'user', text: lastUserText });
                                const sessInfo = activeSessions.get(callSid);
                                if (sessInfo) sessInfo.turnCount++;
                                // Log user utterance
                                await callLogger.debug(callSid, 'user-utterance', `User said: ${lastUserText.substring(0, 100)}`, {
                                    textLength: lastUserText.length,
                                    turnCount: sessInfo?.turnCount || 0,
                                });
                            }
                            lastUserText = '';
                        }
                        if (lastAssistantText) {
                            conversationHistory.push({ role: 'assistant', text: lastAssistantText });
                            console.log(`History saved [ASSISTANT]: ${lastAssistantText.substring(0, 80)}${lastAssistantText.length > 80 ? '...' : ''} (total: ${conversationHistory.length})`);
                            // Append to DynamoDB call record
                            if (callSid) {
                                callRecords.appendTranscript(callSid, { role: 'assistant', text: lastAssistantText });
                                const sessInfo = activeSessions.get(callSid);
                                if (sessInfo) sessInfo.turnCount++;
                                // Log assistant response
                                await callLogger.debug(callSid, 'assistant-response', `Assistant said: ${lastAssistantText.substring(0, 100)}`, {
                                    textLength: lastAssistantText.length,
                                    turnCount: sessInfo?.turnCount || 0,
                                });
                            }
                            // Clear after saving to prevent duplicates
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

                // Handle special case: support tool transfers call
                if (data.toolName == 'support') {
                    console.log(`Transfering call id ${callSid}`);
                    try {
                        await twClient.calls(callSid).update({twiml: sipTwiml});
                    } catch (error) {
                        console.log(error);
                    }
                }

                // Log RAG tool usage
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

                // Log RAG tool results
                if (data.result) {
                    try {
                        const result = typeof data.result === 'string' ? JSON.parse(data.result) : data.result;

                        if (result.documentsFound !== undefined) {
                            // This is a RAG tool result
                            console.log(`[RAG Tool] Retrieved ${result.documentsFound} documents in ${result.retrieveTimeMs}ms`);

                            if (result.success && result.documents) {
                                const retrievedDocs = result.documents.map((doc: any, idx: number) => ({
                                    index: idx + 1,
                                    relevance: doc.relevance,
                                    preview: doc.content.substring(0, 150) + (doc.content.length > 150 ? '...' : ''),
                                    source: doc.source
                                }));

                                callLogger.info(callSid, 'rag-tool-success', `RAG search successful - found ${result.documentsFound} documents`, {
                                    query: result.query,
                                    retrieveTime: `${result.retrieveTimeMs}ms`,
                                    documentsFound: result.documentsFound,
                                    documents: retrievedDocs
                                }).catch(err => console.error('Failed to log RAG tool success:', err));
                            } else {
                                callLogger.warn(callSid, 'rag-tool-no-results', `RAG search returned no results`, {
                                    query: result.query,
                                    message: result.message
                                }).catch(err => console.error('Failed to log RAG no results:', err));
                            }
                        }
                    } catch (err) {
                        console.error('[RAG Tool] Failed to parse tool result:', err);
                    }
                }
            });

            sess.onEvent('streamComplete', () => {
                console.log('Stream completed for client:', sess.streamSid);
            });

            sess.onEvent('error', async (data) => {
                console.error('Error in session:', data);

                // Check if this is a ModelStreamErrorException and we should retry
                const errorDetails = data.details || '';
                const isModelStreamError = errorDetails.includes('ModelStreamErrorException') ||
                                          errorDetails.includes('encountered an unexpected error');

                if (isModelStreamError) {
                    console.log('Detected ModelStreamErrorException, attempting retry...');

                    // Log model stream error
                    if (callSid) {
                        await callLogger.warn(callSid, 'model-stream-error', 'ModelStreamErrorException occurred, retrying session', {
                            errorDetails,
                            retryCount: retryCount
                        });
                    }

                    const retried = await retrySession();
                    if (!retried) {
                        console.error('Retry failed or not applicable, call will disconnect');

                        // Log retry failure
                        if (callSid) {
                            await callLogger.error(callSid, 'retry-failed', 'Session retry failed after ModelStreamErrorException', {
                                errorDetails,
                                retryCount: retryCount
                            });
                        }
                    }
                } else {
                    console.error('Non-retryable error:', errorDetails);

                    // Log non-retryable error
                    if (callSid) {
                        await callLogger.error(callSid, 'non-retryable-error', 'Non-retryable error occurred', {
                            errorDetails
                        });
                    }
                }
            });
        };

        // Initialize event handlers for the first session
        setupSessionHandlers(session);



    });
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

fastify.listen({ host: '0.0.0.0', port: PORT }, (err) => {
    if (err) {
        console.error(err);
        process.exit(1);
    }
    console.log(`Server is listening on port ${PORT}`);
});

// Graceful shutdown on SIGTERM (sent by ECS when stopping tasks)
process.on('SIGTERM', async () => {
    console.log('SIGTERM received, shutting down gracefully...');
    await fastify.close();
    process.exit(0);
});
