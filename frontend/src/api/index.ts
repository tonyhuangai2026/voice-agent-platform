import axios from 'axios';
import type {
  TranscriptListResponse,
  TranscriptDetail,
  ContactListResponse,
  Contact,
  AllRecordsResponse,
  AnalysisResponse,
  GetAnalysisResponse,
  Customer,
  CustomerListResponse,
  ImportCustomersResponse,
  CallResponse,
  BatchCallResponse,
  FlowConfig,
  FlowListResponse,
  PromptConfig,
  PromptListResponse,
  EcsStatus,
  ActiveCallsSummary,
  CallRecordsResponse,
  DynamoCallRecord,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:3001';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function listAllRecords(limit = 50, days = 7): Promise<AllRecordsResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    days: String(days)
  });
  const response = await api.get<AllRecordsResponse>(`/api/records?${params}`);
  return response.data;
}

export async function listContacts(limit = 50, channel = 'VOICE', days = 7): Promise<ContactListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    channel,
    days: String(days)
  });
  const response = await api.get<ContactListResponse>(`/api/contacts?${params}`);
  return response.data;
}

export async function getContact(contactId: string): Promise<Contact> {
  const response = await api.get<Contact>(`/api/contacts/${contactId}`);
  return response.data;
}

export async function listTranscripts(limit = 50, days = 7): Promise<TranscriptListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    days: String(days)
  });
  const response = await api.get<TranscriptListResponse>(`/api/transcripts?${params}`);
  return response.data;
}

export async function getTranscript(contactId: string): Promise<TranscriptDetail> {
  const response = await api.get<TranscriptDetail>(`/api/transcripts/${contactId}`);
  return response.data;
}

export async function analyzeConversation(contactId: string): Promise<AnalysisResponse> {
  const response = await api.post<AnalysisResponse>(`/api/analyze/${contactId}`);
  return response.data;
}

export async function getAnalysis(contactId: string): Promise<GetAnalysisResponse> {
  const response = await api.get<GetAnalysisResponse>(`/api/analysis/${contactId}`);
  return response.data;
}

// Customer Management APIs
export async function importCustomers(csvContent: string): Promise<ImportCustomersResponse> {
  const response = await api.post<ImportCustomersResponse>('/api/customers/import', {
    csv_content: csvContent
  });
  return response.data;
}

export async function listCustomers(status?: string, limit = 100): Promise<CustomerListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) {
    params.append('status', status);
  }
  const response = await api.get<CustomerListResponse>(`/api/customers?${params}`);
  return response.data;
}

export async function getCustomer(customerId: string): Promise<Customer> {
  const response = await api.get<Customer>(`/api/customers/${customerId}`);
  return response.data;
}

export async function updateCustomer(customerId: string, data: Partial<Customer>): Promise<Customer> {
  const response = await api.put<Customer>(`/api/customers/${customerId}`, data);
  return response.data;
}

export async function deleteCustomer(customerId: string): Promise<{ message: string }> {
  const response = await api.delete<{ message: string }>(`/api/customers/${customerId}`);
  return response.data;
}

export async function makeCall(customerId: string, flowId: string): Promise<CallResponse> {
  const response = await api.post<CallResponse>(`/api/call/${customerId}`, {
    flow_id: flowId
  });
  return response.data;
}

export async function makeBatchCall(customerIds: string[], flowId: string): Promise<BatchCallResponse> {
  const response = await api.post<BatchCallResponse>('/api/call/batch', {
    customer_ids: customerIds,
    flow_id: flowId
  });
  return response.data;
}

// Flow Configuration APIs
export async function listFlows(isActive?: boolean): Promise<FlowListResponse> {
  const params = new URLSearchParams();
  if (isActive !== undefined) {
    params.append('is_active', String(isActive));
  }
  const response = await api.get<FlowListResponse>(`/api/flows${params.toString() ? '?' + params : ''}`);
  return response.data;
}

export async function getFlow(flowId: string): Promise<FlowConfig> {
  const response = await api.get<FlowConfig>(`/api/flows/${flowId}`);
  return response.data;
}

export async function createFlow(data: Omit<FlowConfig, 'flow_id' | 'created_at' | 'updated_at'>): Promise<FlowConfig> {
  const response = await api.post<FlowConfig>('/api/flows', data);
  return response.data;
}

export async function updateFlow(flowId: string, data: Partial<FlowConfig>): Promise<FlowConfig> {
  const response = await api.put<FlowConfig>(`/api/flows/${flowId}`, data);
  return response.data;
}

export async function deleteFlow(flowId: string): Promise<{ message: string }> {
  const response = await api.delete<{ message: string }>(`/api/flows/${flowId}`);
  return response.data;
}

// Prompt Configuration APIs
export async function listPrompts(isActive?: boolean): Promise<PromptListResponse> {
  const params = new URLSearchParams();
  if (isActive !== undefined) {
    params.append('is_active', String(isActive));
  }
  const response = await api.get<PromptListResponse>(`/api/prompts${params.toString() ? '?' + params : ''}`);
  return response.data;
}

export async function getPrompt(promptId: string): Promise<PromptConfig> {
  const response = await api.get<PromptConfig>(`/api/prompts/${promptId}`);
  return response.data;
}

export async function createPrompt(data: Omit<PromptConfig, 'prompt_id' | 'created_at' | 'updated_at'>): Promise<PromptConfig> {
  const response = await api.post<PromptConfig>('/api/prompts', data);
  return response.data;
}

export async function updatePrompt(promptId: string, data: Partial<PromptConfig>): Promise<PromptConfig> {
  const response = await api.put<PromptConfig>(`/api/prompts/${promptId}`, data);
  return response.data;
}

export async function deletePrompt(promptId: string): Promise<{ message: string }> {
  const response = await api.delete<{ message: string }>(`/api/prompts/${promptId}`);
  return response.data;
}

// === Monitoring & Call Records APIs ===

const VOICE_SERVER_BASE = import.meta.env.VITE_VOICE_SERVER_BASE || 'http://localhost:3000';

export async function getEcsStatus(): Promise<EcsStatus> {
  const response = await api.get<EcsStatus>('/api/monitor/ecs-status');
  return response.data;
}

export async function getActiveCallsSummary(): Promise<ActiveCallsSummary> {
  const response = await api.get<ActiveCallsSummary>('/api/monitor/active-calls');
  return response.data;
}

export async function listCallRecords(params?: {
  status?: string;
  limit?: number;
  days?: number;
}): Promise<CallRecordsResponse> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.append('status', params.status);
  if (params?.limit) searchParams.append('limit', String(params.limit));
  if (params?.days) searchParams.append('days', String(params.days));
  const qs = searchParams.toString();
  const response = await api.get<CallRecordsResponse>(`/api/call-records${qs ? '?' + qs : ''}`);
  return response.data;
}

export async function getCallRecord(callSid: string): Promise<DynamoCallRecord> {
  const response = await api.get<DynamoCallRecord>(`/api/call-records/${callSid}`);
  return response.data;
}

export function createLiveTranscriptStream(callSid: string): EventSource {
  return new EventSource(`${VOICE_SERVER_BASE}/api/live-transcript/${callSid}`);
}
