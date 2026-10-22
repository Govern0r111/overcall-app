import { AuthUser, Session } from "@supabase/supabase-js";
import { authConfigError, supabase } from "../lib/supabase";

export type { AuthUser };

export interface AuthClient {
  signup(email: string, password: string): Promise<{ user: AuthUser; needsEmailConfirmation: boolean }>;
  login(email: string, password: string): Promise<AuthUser>;
  loginWithGoogle(): Promise<void>;
  logout(): Promise<void>;
  me(): Promise<AuthUser | null>;
  getSession(): Promise<Session | null>;
  getAccessToken(): Promise<string | null>;
  requestPasswordReset(email: string): Promise<void>;
  updatePassword(password: string): Promise<void>;
  continueAsDemo(): Promise<AuthUser>;
  onAuthStateChange(callback: (user: AuthUser | null) => void): () => void;
}

export const SESSION_KEY = "overcall-demo-session";

function demoUser(email = "demo@overcall.local"): AuthUser {
  return {
    id: "demo-user",
    aud: "authenticated",
    role: "authenticated",
    email,
    app_metadata: {},
    user_metadata: { name: "demo", is_demo: true },
    created_at: new Date().toISOString(),
  };
}

function notifyMockSession(user: AuthUser | null) {
  window.dispatchEvent(new CustomEvent("overcall-auth-change", { detail: user }));
}

function normalizedEmail(email: string) {
  return email.trim().toLowerCase();
}

function assertAuthConfigured() {
  if (authConfigError) throw new Error(authConfigError);
}

export const authClient: AuthClient = {
  async signup(email, password) {
    assertAuthConfigured();
    if (supabase) {
      const { data, error } = await supabase.auth.signUp({ email, password });
      if (error || !data.user) throw error ?? new Error("Unable to create your account.");
      return { user: data.user, needsEmailConfirmation: data.session === null };
    }
    const address = normalizedEmail(email);
    if (address === "taken@example.com") throw new Error("An account with this email already exists. Try signing in.");
    const user = demoUser(address);
    localStorage.setItem(SESSION_KEY, JSON.stringify({ email: address }));
    notifyMockSession(user);
    return { user, needsEmailConfirmation: false };
  },
  async login(email, password) {
    assertAuthConfigured();
    if (supabase) {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });
      if (error || !data.user) throw error ?? new Error("Unable to sign in.");
      return data.user;
    }
    if (!password) throw new Error("Enter your password.");
    if (normalizedEmail(email) === "wrong@example.com") {
      throw new Error("That email and password do not match. Check them and try again, or reset your password.");
    }
    const address = normalizedEmail(email);
    const user = demoUser(address);
    localStorage.setItem(SESSION_KEY, JSON.stringify({ email: address }));
    notifyMockSession(user);
    return user;
  },
  async loginWithGoogle() {
    assertAuthConfigured();
    if (!supabase) throw new Error("Google sign-in is not available in demo mode.");
    const next = new URLSearchParams(window.location.search).get("next");
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next ?? "/app")}` },
    });
    if (error) throw error;
  },
  async logout() {
    assertAuthConfigured();
    if (supabase) {
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
    }
    localStorage.removeItem(SESSION_KEY);
    notifyMockSession(null);
  },
  async me() {
    assertAuthConfigured();
    if (supabase) {
      const { data, error } = await supabase.auth.getUser();
      if (error && error.name !== "AuthSessionMissingError") throw error;
      return data.user;
    }
    const session = localStorage.getItem(SESSION_KEY);
    if (!session) return null;
    try {
      return demoUser(JSON.parse(session).email);
    } catch {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
  },
  async getSession() {
    assertAuthConfigured();
    if (supabase) {
      const { data, error } = await supabase.auth.getSession();
      if (error) throw error;
      return data.session;
    }
    return null;
  },
  async getAccessToken() {
    assertAuthConfigured();
    if (!supabase) return null;
    const { data, error } = await supabase.auth.getSession();
    if (error) throw error;
    return data.session?.access_token ?? null;
  },
  async requestPasswordReset(email) {
    assertAuthConfigured();
    if (!supabase) {
      throw new Error("Password reset email is unavailable in demo mode. Configure Supabase Auth to send reset links.");
    }
    const { error } = await supabase.auth.resetPasswordForEmail(normalizedEmail(email), {
      redirectTo: `${window.location.origin}/reset`,
    });
    if (error) throw error;
  },
  async updatePassword(password) {
    assertAuthConfigured();
    if (!supabase) {
      throw new Error("Password updates require a Supabase password-reset session.");
    }
    const { error } = await supabase.auth.updateUser({ password });
    if (error) throw error;
  },
  async continueAsDemo() {
    assertAuthConfigured();
    if (supabase) throw new Error("Demo sessions are unavailable while Supabase Auth is configured.");
    const user = demoUser();
    localStorage.setItem(SESSION_KEY, JSON.stringify({ email: user.email }));
    notifyMockSession(user);
    return user;
  },
  onAuthStateChange(callback) {
    if (authConfigError) return () => undefined;
    if (supabase) {
      const { data } = supabase.auth.onAuthStateChange((_event, session) => callback(session?.user ?? null));
      return () => data.subscription.unsubscribe();
    }
    const onChange = (event: Event) => callback((event as CustomEvent<AuthUser | null>).detail);
    const onStorage = (event: StorageEvent) => {
      if (event.key === SESSION_KEY) void this.me().then(callback);
    };
    window.addEventListener("overcall-auth-change", onChange);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("overcall-auth-change", onChange);
      window.removeEventListener("storage", onStorage);
    };
  },
};
