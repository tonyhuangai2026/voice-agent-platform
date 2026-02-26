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

export interface UploadUrlResponse {
  uploadUrl: string;
  filename: string;
  bucket: string;
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
  label_zh: string;
  label_es: string;
}

export interface AnalysisResult {
  contactId: string;
  analyzedAt: string;
  intentionTag: TagLabel;
  personalityTags: TagLabel[];
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
  project_id: string;
  customer_name: string;
  phone_number: string;
  email?: string;
  status: 'pending' | 'calling' | 'called' | 'completed' | 'failed';
  call_count: number;
  last_call_time?: string;
  notes?: string;
  tags?: string[];
  voice_id?: string;
  prompt_id?: string;
  custom_fields?: Record<string, any>;
  latest_call_labels?: CallLabels;
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
  project_id: string;
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
  project_id: string;
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

// Voice-server active calls
export interface ActiveCall {
  callSid: string;
  streamSid: string;
  customerPhone: string;
  customerName: string;
  voiceId: string;
  startTime: string;
  turnCount: number;
}

export interface ActiveCallsResponse {
  activeCalls: ActiveCall[];
  totalActive: number;
}

// DynamoDB call records
export interface DynamoCallRecord {
  callSid: string;
  project_id?: string;
  streamSid?: string;
  status: string;
  customerPhone?: string;
  customerName?: string;
  voiceId?: string;
  startTime: string;
  endTime?: string;
  endReason?: string;
  turnCount: number;
  transcript?: Array<{
    role: 'user' | 'assistant';
    text: string;
    timestamp: string;
  }>;
  labels?: CallLabels;
  auto_labeled_at?: string;
}

export interface DynamoCallRecordsResponse {
  records: DynamoCallRecord[];
  count: number;
}

// Projects
export interface Project {
  project_id: string;
  project_name: string;
  project_type: 'collection' | 'marketing' | 'survey' | 'notification' | 'other';
  description: string;
  status: 'active' | 'inactive' | 'archived';
  default_prompt_id?: string;
  default_flow_id?: string;
  settings?: {
    voice_id?: string;
    language?: string;
    temperature?: number;
  };
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  projects: Project[];
  count: number;
}

export interface ProjectStats {
  total_customers: number;
  total_calls: number;
  active_calls: number;
  success_rate: number;
  avg_call_duration: number;
}

// Labels
export interface LabelConfig {
  label_id: string;
  project_id: string;
  label_name: string;
  label_type: 'single' | 'multiple';
  options: string[];
  description?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LabelListResponse {
  labels: LabelConfig[];
  count: number;
}

export interface CallLabels {
  [labelId: string]: string | string[];
}
