// Login with a Supabase email magic link (free tier). Active only when both env vars are set;
// otherwise Kshetra runs in single-user local mode with no sign-in.
import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY;
export const supabase = url && key ? createClient(url, key) : null;
export const authEnabled = Boolean(supabase);

export async function accessToken() {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function sendMagicLink(email) {
  const { error } = await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: window.location.origin } });
  if (error) throw error;
}

export async function signOut() {
  if (supabase) await supabase.auth.signOut();
  try {
    await caches.delete("kshetra-api");          // never leave one farmer's data for the next person
  } catch {
    /* no cache storage */
  }
}
