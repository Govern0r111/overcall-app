export const env = {
  siteUrl: import.meta.env.VITE_SITE_URL || "https://overcall.app",
  backendUrl: import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000",
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL || "",
  supabaseAnonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || "",
  authMode:
    import.meta.env.VITE_AUTH_MODE === "mock" || import.meta.env.VITE_AUTH_MODE === "supabase"
      ? import.meta.env.VITE_AUTH_MODE
      : import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_ANON_KEY
        ? "supabase"
        : "mock",
};
