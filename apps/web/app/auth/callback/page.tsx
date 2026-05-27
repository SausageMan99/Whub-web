"use client";

import { useEffect, useState } from "react";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

function safeNext(path: string | null) {
  if (!path || !path.startsWith("/") || path.startsWith("//")) return "/dashboard";
  return path;
}

export default function AuthCallbackPage() {
  const [message, setMessage] = useState("Connexion sécurisée en cours…");

  useEffect(() => {
    const completeLogin = async () => {
      const supabase = createSupabaseBrowserClient();
      const url = new URL(window.location.href);
      const next = safeNext(url.searchParams.get("next"));
      const code = url.searchParams.get("code");
      const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
      const accessToken = hash.get("access_token");
      const refreshToken = hash.get("refresh_token");

      try {
        if (code) {
          const { error } = await supabase.auth.exchangeCodeForSession(code);
          if (error) throw error;
        } else if (accessToken && refreshToken) {
          const { error } = await supabase.auth.setSession({
            access_token: accessToken,
            refresh_token: refreshToken,
          });
          if (error) throw error;
        } else {
          throw new Error("Lien magique incomplet ou expiré");
        }

        window.location.replace(next);
      } catch (error) {
        console.error("Supabase auth callback failed", error);
        setMessage("Lien magique invalide ou expiré. Redirection vers la connexion…");
        window.setTimeout(() => {
          window.location.replace("/login?error=auth_callback");
        }, 1200);
      }
    };

    void completeLogin();
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center bg-porcelain px-6 text-ink">
      <section className="max-w-md rounded-[2rem] border border-white/75 bg-white/85 p-8 text-center shadow-soft">
        <p className="text-xs font-black uppercase tracking-[0.28em] text-whub">W hub CV Factory</p>
        <h1 className="mt-4 text-3xl font-black tracking-[-0.05em]">Connexion</h1>
        <p className="mt-3 text-sm font-semibold leading-6 text-ink/55">{message}</p>
      </section>
    </main>
  );
}
