import axios from 'axios';
import type {
  TranscriptListResponse,
  TranscriptDetail,
  UploadUrlResponse,
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
  ActiveCallsResponse,
  DynamoCallRecordsResponse,
  Project,
  ProjectListResponse,
  ProjectStats,
  LabelConfig,
  LabelListResponse,
  CallLabels,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE;

if (!API_BASE) {
  throw new Error('VITE_API_BASE environment variable is not set. Please configure it in .env file.');
}

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to all requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 errors globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid, clear it
      localStorage.removeItem('auth_token');
      window.location.reload(); // Reload to trigger login
    }
    return Promise.reject(error);
  }
);

export async function listAllRecords(limit = 50, days = 7): Promise<AllRecordsResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    days: String(days)
  });
  const response = await api.get<AllRecordsResponse>(`/api/records?${params}`);
  return response.data;
}

export async function getUploadUrl(filename: string): Promise<UploadUrlResponse> {
  const response = await api.post<UploadUrlResponse>('/api/upload-url', { filename });
  return response.data;
}

export async function uploadFile(uploadUrl: string, file: File): Promise<void> {
  await axios.put(uploadUrl, file, {
    headers: {
      'Content-Type': 'text/csv',
    },
  });
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
export async function importCustomers(csvContent: string, projectId?: string): Promise<ImportCustomersResponse> {
  const response = await api.post<ImportCustomersResponse>('/api/customers/import', {
    csv_content: csvContent,
    project_id: projectId
  });
  return response.data;
}

export async function listCustomers(status?: string, limit = 100, projectId?: string): Promise<CustomerListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) {
    params.append('status', status);
  }
  if (projectId) {
    params.append('project_id', projectId);
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
export async function listFlows(isActive?: boolean, projectId?: string): Promise<FlowListResponse> {
  const params = new URLSearchParams();
  if (isActive !== undefined) {
    params.append('is_active', String(isActive));
  }
  if (projectId) {
    params.append('project_id', projectId);
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
export async function listPrompts(isActive?: boolean, projectId?: string): Promise<PromptListResponse> {
  const params = new URLSearchParams();
  if (isActive !== undefined) {
    params.append('is_active', String(isActive));
  }
  if (projectId) {
    params.append('project_id', projectId);
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

// Voice Server APIs
const VOICE_SERVER_BASE = import.meta.env.VITE_VOICE_SERVER_BASE;

if (!VOICE_SERVER_BASE) {
  throw new Error('VITE_VOICE_SERVER_BASE environment variable is not set. Please configure it in .env file.');
}

// Create a separate axios instance for voice server (different domain, needs CORS)
const voiceServerApi = axios.create({
  baseURL: VOICE_SERVER_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: false,
});

export async function getActiveCalls(): Promise<ActiveCallsResponse> {
  const response = await voiceServerApi.get<ActiveCallsResponse>('/api/active-calls');
  return response.data;
}

export async function listCallRecords(limit = 20, status?: string): Promise<DynamoCallRecordsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) {
    params.append('status', status);
  }
  const response = await api.get<DynamoCallRecordsResponse>(`/api/call-records?${params}`);
  return response.data;
}

export async function deleteCallRecord(callSid: string): Promise<{ message: string; callSid: string }> {
  const response = await api.delete<{ message: string; callSid: string }>(`/api/call-records/${callSid}`);
  return response.data;
}

export function createLiveTranscriptStream(callSid: string): EventSource {
  const url = `${VOICE_SERVER_BASE}/api/live-transcript/${callSid}`;
  console.log(`Creating SSE connection to: ${url}`);
  return new EventSource(url);
}

// Project Management APIs
export async function listProjects(status?: string): Promise<ProjectListResponse> {
  const params = status ? { status } : {};
  const response = await api.get<ProjectListResponse>('/api/projects', { params });
  return response.data;
}

export async function getProject(projectId: string): Promise<Project> {
  const response = await api.get<Project>(`/api/projects/${projectId}`);
  return response.data;
}

export async function createProject(project: Partial<Project>): Promise<{ message: string; project: Project }> {
  const response = await api.post<{ message: string; project: Project }>('/api/projects', project);
  return response.data;
}

export async function updateProject(projectId: string, updates: Partial<Project>): Promise<{ message: string; project: Project }> {
  const response = await api.put<{ message: string; project: Project }>(`/api/projects/${projectId}`, updates);
  return response.data;
}

export async function deleteProject(projectId: string): Promise<{ message: string }> {
  const response = await api.delete<{ message: string }>(`/api/projects/${projectId}`);
  return response.data;
}

export async function getProjectStats(projectId: string): Promise<ProjectStats> {
  const response = await api.get<ProjectStats>(`/api/projects/${projectId}/stats`);
  return response.data;
}

// Label APIs
export async function listLabels(projectId?: string, isActive?: boolean): Promise<LabelListResponse> {
  const params = new URLSearchParams();
  if (projectId) params.append('project_id', projectId);
  if (isActive !== undefined) params.append('is_active', String(isActive));
  const response = await api.get<LabelListResponse>(`/api/labels${params.toString() ? '?' + params : ''}`);
  return response.data;
}

export async function getLabel(labelId: string): Promise<LabelConfig> {
  const response = await api.get<LabelConfig>(`/api/labels/${labelId}`);
  return response.data;
}

export async function createLabel(label: Omit<LabelConfig, 'label_id' | 'created_at' | 'updated_at'>): Promise<{ message: string; label: LabelConfig }> {
  const response = await api.post<{ message: string; label: LabelConfig }>('/api/labels', label);
  return response.data;
}

export async function updateLabel(labelId: string, updates: Partial<LabelConfig>): Promise<{ message: string; label: LabelConfig }> {
  const response = await api.put<{ message: string; label: LabelConfig }>(`/api/labels/${labelId}`, updates);
  return response.data;
}

export async function deleteLabel(labelId: string): Promise<{ message: string }> {
  const response = await api.delete<{ message: string }>(`/api/labels/${labelId}`);
  return response.data;
}

export async function updateCallLabels(callSid: string, labels: CallLabels): Promise<{ message: string; callSid: string; labels: CallLabels }> {
  const response = await api.put<{ message: string; callSid: string; labels: CallLabels }>(`/api/call-records/${callSid}/labels`, { labels });
  return response.data;
}

export async function autoLabelCall(callSid: string): Promise<{ message: string; callSid: string; labels: CallLabels }> {
  const response = await api.post<{ message: string; callSid: string; labels: CallLabels }>(`/api/call-records/${callSid}/auto-label`);
  return response.data;
}

export async function getCallRecordingUrl(callSid: string): Promise<{ downloadUrl: string; callSid: string; filename: string; expiresIn: number }> {
  const response = await api.get<{ downloadUrl: string; callSid: string; filename: string; expiresIn: number }>(`/api/call-records/${callSid}/recording`);
  return response.data;
}

// Call Logs API
export interface CallLog {
  callSid: string;
  timestamp: string;
  level: 'info' | 'warn' | 'error' | 'debug';
  event: string;
  message: string;
  metadata?: Record<string, any>;
}

export interface CallLogsResponse {
  callSid: string;
  logs: CallLog[];
  count: number;
}

export async function getCallLogs(callSid: string): Promise<CallLogsResponse> {
  const response = await api.get<CallLogsResponse>(`/api/call-records/${callSid}/logs`);
  return response.data;
}
