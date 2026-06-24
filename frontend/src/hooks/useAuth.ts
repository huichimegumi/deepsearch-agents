import { useCallback, useEffect, useState } from "react";
import {
  clearAuthSession,
  fetchCurrentUser,
  getAuthToken,
  getStoredUser,
  login,
  register,
  storeAuthSession
} from "../lib/auth";
import type { AuthUser } from "../types";

export function useAuth() {
  const [token, setToken] = useState(getAuthToken);
  const [user, setUser] = useState<AuthUser | null>(getStoredUser);
  const [isChecking, setIsChecking] = useState(Boolean(getAuthToken()));

  useEffect(() => {
    if (!token) {
      setIsChecking(false);
      return;
    }

    let disposed = false;
    setIsChecking(true);
    fetchCurrentUser()
      .then((currentUser) => {
        if (!disposed) {
          setUser(currentUser);
        }
      })
      .catch(() => {
        if (!disposed) {
          clearAuthSession();
          setToken("");
          setUser(null);
        }
      })
      .finally(() => {
        if (!disposed) {
          setIsChecking(false);
        }
      });

    return () => {
      disposed = true;
    };
  }, [token]);

  const signIn = useCallback(async (username: string, password: string) => {
    const response = await login(username, password);
    storeAuthSession(response);
    setToken(response.access_token);
    setUser(response.user);
  }, []);

  const signUp = useCallback(
    async (username: string, password: string, displayName: string) => {
      const response = await register(username, password, displayName);
      storeAuthSession(response);
      setToken(response.access_token);
      setUser(response.user);
    },
    []
  );

  const signOut = useCallback(() => {
    clearAuthSession();
    setToken("");
    setUser(null);
  }, []);

  return {
    isChecking,
    isAuthenticated: Boolean(token && user),
    signIn,
    signOut,
    signUp,
    token,
    user
  };
}
