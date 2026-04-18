import { createClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL || 'https://hytblxitlqnrkgsaifez.supabase.co';
const key = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh5dGJseGl0bHFucmtnc2FpZmV6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY0ODExNzgsImV4cCI6MjA5MjA1NzE3OH0.P2sYWRANqNlnh4imWrELjsUErzqq8ye6a1Vc85uwIxY';

export const supabase = url && key ? createClient(url, key) : null;
export const hasSupabase = Boolean(supabase);
