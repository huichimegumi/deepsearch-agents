import { API_BASE_URL } from "./config";
import type { AuthResponse, AuthUser } from "../types";

const TOKEN_KEY = "deepsearch.access_token";
const USER_KEY = "deepsearch.user";

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export function getAuthToken(): string {
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function storeAuthSession(response: AuthResponse): void {
  window.localStorage.setItem(TOKEN_KEY, response.access_token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(response.user));
}

export function clearAuthSession(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

export function getStoredUser(): AuthUser | null {
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

async function requestAuth<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    }
  });
  const payload = await response.json();
  if (!response.ok) {
    const detail = typeof payload?.detail === "string" ? payload.detail : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}

export function login(username: string, password: string): Promise<AuthResponse> {
  return requestAuth<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });
}

export function register(
  username: string,
  password: string,
  displayName: string
): Promise<AuthResponse> {
  return requestAuth<AuthResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, display_name: displayName })
  });
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const token = getAuthToken();
  const response = await fetch(apiUrl("/api/auth/me"), {
    headers: {
      Authorization: `Bearer ${token}`
    }
  });
  const payload = await response.json();
  if (!response.ok) {
    const detail = typeof payload?.detail === "string" ? payload.detail : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload as AuthUser;
}
