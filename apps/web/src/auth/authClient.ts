import { AuthUser, Session } from "@supabase/supabase-js";
import { hasSupabase, supabase } from "../lib/supabase";

export type { AuthUser };

export interface AuthClient {
  signup(email: string, password: string): Promise<AuthUser>;
  login(email: string, password: string): Promise<AuthUser>;
  loginWithGoogle(): Promise<void>;
  logout(): Promise<void>;
  me(): Promise<AuthUser | null>;
  getSession(): Promise<Session | null>;
}

const SESSION_KEY = "overcall-demo-session";

function demoUser(): AuthUser {
  return { id: "demo-user", aud: "authenticated", role: "authenticated", email: "demo@overcall.local", app_metadata: {}, user_metadata: { name: "demo" }, created_at: new Date().toISOString() };
}

export const authClient: AuthClient = {
  async signup(email, password) {
    if (supabase) {
      const { data, error } = await supabase.auth.signUp({ email, password });
      if (error || !data.user) throw error ?? new Error("Unable to create your account.");
      return data.user;
    }
    localStorage.setItem(SESSION_KEY, JSON.stringify({ email }));
    return { ...demoUser(), email };
  },
  async login(email, password) {
    if (supabase) {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });
      if (error || !data.user) throw error ?? new Error("Unable to sign in.");
      return data.user;
    }
    if (!password) throw new Error("Enter your password.");
    localStorage.setItem(SESSION_KEY, JSON.stringify({ email }));
    return { ...demoUser(), email };
  },
  async loginWithGoogle() {
    if (!supabase) throw new Error("Google sign-in is not available in demo mode.");
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/app` },
    });
    if (error) throw error;
  },
  async logout() {
    if (supabase) {
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
    }
    localStorage.removeItem(SESSION_KEY);
  },
  async me() {
    if (supabase) {
      const { data, error } = await supabase.auth.getUser();
      if (error && error.name !== "AuthSessionMissingError") throw error;
      return data.user;
    }
    return localStorage.getItem(SESSION_KEY) ? demoUser() : null;
  },
  async getSession() {
    if (supabase) {
      const { data, error } = await supabase.auth.getSession();
      if (error) throw error;
      return data.session;
    }
    return hasSupabase ? null : localStorage.getItem(SESSION_KEY) ? ({ user: demoUser() } as Session) : null;
  },
};
