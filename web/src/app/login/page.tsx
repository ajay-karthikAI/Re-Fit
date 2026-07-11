"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { login, register } from "@/lib/api";
import { useDevUser } from "@/components/providers/dev-user-provider";

type Mode = "login" | "new";

/**
 * Sign-in gate between the landing hero and the workspace. Login verifies the
 * password against /auth/login (bcrypt-backed) and stores the issued bearer
 * session; New registers via /auth/register. A pre-auth account (dev picker /
 * seed scripts) has no password yet — registering with its email claims it.
 */
export default function LoginPage() {
  const router = useRouter();
  const { setSelectedUserId } = useDevUser();

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    const address = email.trim().toLowerCase();
    if (!address) {
      setError("Enter your email.");
      return;
    }
    if (mode === "new" && password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (!password) {
      setError("Enter your password.");
      return;
    }

    setPending(true);
    try {
      const authSession =
        mode === "login" ? await login(address, password) : await register(address, password);
      setSelectedUserId(authSession.user.id);
      router.push("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed.");
      setPending(false);
    }
  };

  const inputCls =
    "h-11 w-full rounded-[10px] border border-silver/[0.18] bg-background/60 px-3.5 text-sm text-text outline-none transition placeholder:text-faint focus:border-accent/60";

  return (
    <main
      className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-6"
      style={{
        backgroundImage:
          "linear-gradient(rgba(201,205,211,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(201,205,211,0.045) 1px, transparent 1px)",
        backgroundSize: "44px 44px"
      }}
    >
      {/* Gold glow pooling behind the sign-in card. */}
      <div
        aria-hidden
        className="pointer-events-none absolute left-[62%] top-1/2 h-[620px] w-[620px] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-50 blur-3xl"
        style={{
          background:
            "radial-gradient(circle, rgba(232,196,107,0.22) 0%, rgba(232,196,107,0.06) 45%, transparent 70%)"
        }}
      />

      <div className="relative grid w-full max-w-[1060px] items-center gap-14 lg:grid-cols-[1fr_480px]">
        {/* LEFT: brand + pitch */}
        <div className="flex flex-col items-start">
          <div
            className="anim-rise flex h-20 w-20 items-center justify-center rounded-2xl border border-silver/[0.14] bg-[linear-gradient(160deg,#191510,#0B0A08_70%)] shadow-[0_0_44px_rgba(232,196,107,0.22)]"
            style={{ animationDelay: "0ms" }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="Re-Fit" className="w-14" />
          </div>

          <span
            className="anim-rise mt-7 inline-flex items-center gap-2 rounded-full border border-silver/[0.18] bg-surface px-3.5 py-1.5 text-[13px] font-medium text-silver"
            style={{ animationDelay: "100ms" }}
          >
            <svg width="12" height="14" viewBox="0 0 12 14" fill="none" aria-hidden>
              <path
                d="M6 1 1 3v4c0 3.1 2.1 5.3 5 6 2.9-.7 5-2.9 5-6V3L6 1Z"
                stroke="currentColor"
                strokeWidth="1.3"
                strokeLinejoin="round"
              />
            </svg>
            Private application workspace
          </span>

          <h1
            className="anim-rise mt-5 text-[clamp(32px,3.4vw,44px)] font-bold leading-[1.15] tracking-[-0.02em] text-text"
            style={{ animationDelay: "200ms" }}
          >
            Your resume, kits, and tracker stay with your account.
          </h1>

          <p
            className="anim-rise mt-5 max-w-md text-[15px] leading-7 text-subdued"
            style={{ animationDelay: "300ms" }}
          >
            Sign in to upload your resume, generate tailored application kits, and keep your job
            search history separated from everyone else.
          </p>
        </div>

        {/* RIGHT: sign-in card */}
        <form
          onSubmit={submit}
          className="anim-rise rounded-2xl border border-silver/[0.14] bg-surface/80 p-7 shadow-[0_0_60px_rgba(232,196,107,0.12)] backdrop-blur"
          style={{ animationDelay: "220ms" }}
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2.5 text-lg font-semibold text-text">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
                  <circle cx="8" cy="5" r="3" stroke="currentColor" strokeWidth="1.4" />
                  <path
                    d="M2.5 14c.8-2.6 3-4 5.5-4s4.7 1.4 5.5 4"
                    stroke="currentColor"
                    strokeWidth="1.4"
                    strokeLinecap="round"
                  />
                </svg>
                Sign in
              </div>
              <p className="mt-2 text-[13px] leading-5 text-subdued">
                Use your email and a password with at least 8 characters.
              </p>
            </div>
            <div className="flex shrink-0 rounded-[10px] border border-silver/[0.14] bg-background/60 p-1">
              {(["login", "new"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => {
                    setMode(value);
                    setError(null);
                  }}
                  className={[
                    "rounded-lg px-3.5 py-1.5 text-[13px] font-semibold transition",
                    mode === value
                      ? "bg-gold-gradient text-onaccent"
                      : "text-subdued hover:text-text"
                  ].join(" ")}
                >
                  {value === "login" ? "Login" : "New"}
                </button>
              ))}
            </div>
          </div>

          <label className="mt-6 block text-sm font-medium text-text">
            Email
            <input
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className={`mt-2 ${inputCls}`}
            />
          </label>

          <label className="mt-5 block text-sm font-medium text-text">
            Password
            <input
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              placeholder="8+ characters"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={`mt-2 ${inputCls}`}
            />
          </label>

          {error ? (
            <p className="mt-4 rounded-[10px] border border-danger/40 bg-danger/10 px-3.5 py-2.5 text-[13px] text-danger">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={pending}
            className="mt-6 w-full rounded-[10px] bg-gold-gradient px-4 py-3 text-[15px] font-bold text-onaccent transition enabled:hover:-translate-y-0.5 enabled:hover:shadow-gold disabled:opacity-60"
          >
            {pending
              ? mode === "login"
                ? "Signing in…"
                : "Creating workspace…"
              : "Open My Dashboard"}
          </button>
        </form>
      </div>
    </main>
  );
}
