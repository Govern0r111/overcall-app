import { createClient, SupabaseClient } from "@supabase/supabase-js";
import { env } from "./env";

const url = env.supabaseUrl;
const anonKey = env.supabaseAnonKey;
const configured = Boolean(url && anonKey);

export const authConfigError =
  env.authMode === "supabase" && !configured
    ? "Supabase Auth is selected, but VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are required."
    : null;

export const supabase: SupabaseClient | null =
  env.authMode === "supabase" && configured ? createClient(url, anonKey) : null;

export const hasSupabase = Boolean(supabase);
