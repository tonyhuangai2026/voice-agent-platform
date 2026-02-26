import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE;

if (!API_BASE) {
  throw new Error('VITE_API_BASE environment variable is not set. Please configure it in .env file.');
}

export interface LoginResponse {
  message: string;
  token: string;
  user: {
    user_id: string;
    email: string;
    name: string;
  };
}

export interface RegisterResponse {
  message: string;
  token: string;
  user: {
    user_id: string;
    email: string;
    name: string;
  };
}

export interface VerifyResponse {
  valid: boolean;
  user: {
    user_id: string;
    email: string;
    name: string;
  };
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const response = await axios.post<LoginResponse>(`${API_BASE}/api/auth/login`, {
    email,
    password,
  });
  return response.data;
}

export async function register(
  email: string,
  password: string,
  name: string,
  invite_code: string
): Promise<RegisterResponse> {
  const response = await axios.post<RegisterResponse>(`${API_BASE}/api/auth/register`, {
    email,
    password,
    name,
    invite_code,
  });
  return response.data;
}

export async function verifyToken(token: string): Promise<VerifyResponse> {
  const response = await axios.get<VerifyResponse>(`${API_BASE}/api/auth/verify`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  return response.data;
}
