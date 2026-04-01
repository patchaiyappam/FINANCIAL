const SUPABASE_URL = "https://zqffhhqfipyewcluvixk.supabase.co";

const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpxZmZoaHFmaXB5ZXdjbHV2aXhrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM5MzY5MDAsImV4cCI6MjA4OTUxMjkwMH0.kplOEhd-eo3uQqaCcQgyOUsbks7QALUhhSp3aRlodn4";

const API_BASE_URL = "https://financial-pecc.onrender.com"; // or comment if not deployed

window.supabase = window.supabase.createClient(
  SUPABASE_URL,
  SUPABASE_ANON_KEY
);

// Backward compatibility for existing code using 'db'
window.db = window.supabase;
