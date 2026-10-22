import { createClient, SupabaseClient } from "@supabase/supabase-js";
import { env } from "./env";

const url = env.supabaseUrl;
const anonKey = env.supabaseAnonKey;

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null;

export const hasSupabase = Boolean(supabase);
