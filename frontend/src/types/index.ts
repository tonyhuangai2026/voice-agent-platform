export interface Transcript {
  contactId: string;
  timestamp: string;
  customerPhone?: string;
  systemPhone?: string;
  customerName?: string;
  debtAmount?: string;
  channel?: string;
  initiationMethod?: string;
  disconnectReason?: string;
}

export interface TranscriptListResponse {
  transcripts: Transcript[];
  count: number;
}

export interface ChatMessage {
  id: string;
  content: string;
  timestamp?: string;
  offsetMs?: number;
  role: 'CUSTOMER' | 'SYSTEM' | 'AGENT';
  displayName: string;
  participantId: string;
  sentiment?: string;
}

export interface TranscriptDetail {
  contactId: string;
  instanceId?: string;
  participants?: { ParticipantId: string }[];
  messages: ChatMessage[];
  customerPhone?: string;
  systemPhone?: string;
  customerName?: string;
  debtAmount?: string;
  channel?: string;
  initiationMethod?: string;
  disconnectReason?: string;
}

export interface Contact {
  contactId: string;
  channel: string;
  initiationMethod: string;
  initiationTimestamp: string;
  disconnectTimestamp?: string;
  customerPhone?: string;
  systemPhone?: string;
  customerName?: string;
  debtAmount?: string;
  disconnectReason?: string;
}

export interface ContactListResponse {
  contacts: Contact[];
  count: number;
}

export interface CallRecord {
  contactId: string;
  channel: string;
  initiationMethod: string;
  timestamp: string;
  customerPhone?: string;
  systemPhone?: string;
  customerName?: string;
  debtAmount?: string;
  disconnectReason?: string;
  hasTranscript: boolean;
}

export interface AllRecordsResponse {
  records: CallRecord[];
  count: number;
}

export interface TagLabel {
  code: string;
  label: string;
}

export interface AnalysisResult {
  contactId: string;
  analyzedAt: string;
  outcomeTag: TagLabel;
  behaviorTags: TagLabel[];
  error?: string;
}

export interface AnalysisResponse {
  contactId: string;
  analysis: AnalysisResult;
  analyzedAt: string;
}

export interface GetAnalysisResponse {
  contactId: string;
  analysis?: AnalysisResult;
  exists: boolean;
}

export interface Customer {
  customer_id: string;
  customer_name: string;
  phone_number: string;
  debt_amount: number;
  status: 'pending' | 'calling' | 'called' | 'failed';
  call_count: number;
  last_call_time?: string;
  notes: string;
  voice_id?: string;
  prompt_id?: string;
  created_at: string;
  updated_at: string;
}

export interface CustomerListResponse {
  customers: Customer[];
  count: number;
}

export interface ImportCustomersResponse {
  imported: number;
  updated: number;
  skipped: number;
}

export interface CallResponse {
  message: string;
  contact_id: string;
  customer_id: string;
}

export interface BatchCallResponse {
  success_count: number;
  failed_count: number;
  results: {
    success: Array<{ customer_id: string; contact_id: string }>;
    failed: Array<{ customer_id: string; error: string }>;
  };
}

export interface FlowConfig {
  flow_id: string;
  flow_name: string;
  instance_id: string;
  contact_flow_id: string;
  queue_id: string;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FlowListResponse {
  flows: FlowConfig[];
  count: number;
}

export interface PromptConfig {
  prompt_id: string;
  prompt_name: string;
  prompt_content: string;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PromptListResponse {
  prompts: PromptConfig[];
  count: number;
}

// === Monitoring & Call Records ===

export interface EcsStatus {
  clusterName: string;
  serviceName: string;
  runningCount: number;
  desiredCount: number;
  pendingCount: number;
}

export interface ActiveCall {
  callSid: string;
  streamSid?: string;
  customerPhone: string;
  customerName: string;
  voiceId: string;
  startTime: string;
  turnCount: number;
  instanceId?: string;
}

export interface ActiveCallsSummary {
  activeCalls: ActiveCall[];
  totalActive: number;
}

export interface DynamoCallRecord {
  callSid: string;
  status: 'active' | 'completed' | 'failed';
  customerPhone: string;
  customerName: string;
  voiceId: string;
  startTime: string;
  endTime?: string;
  endReason?: string;
  transcript: Array<{ role: 'user' | 'assistant'; text: string; timestamp: string }>;
  turnCount: number;
  durationMs?: number;
  transcriptCount?: number;
}

export interface CallRecordsResponse {
  records: DynamoCallRecord[];
  count: number;
}

export interface LiveTranscriptEvent {
  type: 'text' | 'status' | 'done';
  role?: 'user' | 'assistant';
  text?: string;
  timestamp?: string;
  reason?: string;
}
