export const env = {
  siteUrl: import.meta.env.VITE_SITE_URL || "https://overcall.app",
  backendUrl: import.meta.env.VITE_BACKEND_URL || "http://localhost:8000",
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL || "",
  supabaseAnonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || "",
};
