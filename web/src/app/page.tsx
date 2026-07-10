"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/** Full-bleed landing hero: centered logo tile over a faint grid, the
 *  wordmark, "The Gold Standard" headline, tagline, and the dashboard CTA.
 *  Everything rises in staggered from below; the CTA fades the hero upward
 *  before handing off to the dashboard (which rises in via the shell). */
export default function HomePage() {
  const router = useRouter();
  const [exiting, setExiting] = useState(false);

  const openDashboard = () => {
    if (exiting) {
      return;
    }
    setExiting(true);
    window.setTimeout(() => router.push("/login"), 260);
  };

  const stagger = (ms: number) => ({ animationDelay: `${ms}ms` });

  return (
    <main
      className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-background px-6 text-center"
      style={{
        backgroundImage:
          "linear-gradient(rgba(201,205,211,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(201,205,211,0.045) 1px, transparent 1px)",
        backgroundSize: "44px 44px"
      }}
    >
      {/* Gold glow pooling behind the logo tile. */}
      <div
        aria-hidden
        className={`pointer-events-none absolute left-1/2 top-1/2 h-[560px] w-[560px] -translate-x-1/2 -translate-y-[62%] rounded-full blur-3xl transition-opacity duration-300 ${
          exiting ? "opacity-0" : "opacity-60"
        }`}
        style={{
          background:
            "radial-gradient(circle, rgba(232,196,107,0.28) 0%, rgba(232,196,107,0.08) 45%, transparent 70%)"
        }}
      />

      <div className={`relative flex flex-col items-center ${exiting ? "anim-exit" : ""}`}>
        <div
          className="anim-rise flex h-56 w-56 items-center justify-center rounded-[28px] border border-silver/[0.14] bg-[linear-gradient(160deg,#191510,#0B0A08_70%)] shadow-[0_0_80px_rgba(232,196,107,0.25),inset_0_1px_0_rgba(201,205,211,0.12)]"
          style={stagger(0)}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="Re-Fit" className="w-40" />
        </div>

        <p
          className="anim-rise mt-8 font-mono text-xs font-medium tracking-[0.32em] text-accent"
          style={stagger(120)}
        >
          RE-FIT
        </p>

        <h1
          className="anim-rise mt-4 text-[clamp(38px,5vw,56px)] font-bold leading-tight tracking-[-0.02em] text-text"
          style={stagger(220)}
        >
          The Gold Standard
        </h1>

        <p
          className="anim-rise mt-4 max-w-xl text-[16px] leading-7 text-subdued"
          style={stagger(320)}
        >
          Turn one resume into a tailored application kit for every job — matched and scored
          against the boards you watch, with the cover letter and follow-ups ready to send.
        </p>

        <button
          type="button"
          onClick={openDashboard}
          className="anim-rise mt-9 rounded-[10px] bg-gold-gradient px-6 py-3 text-[15px] font-bold text-onaccent transition hover:-translate-y-0.5 hover:shadow-gold"
          style={stagger(420)}
        >
          Open Dashboard
        </button>
      </div>
    </main>
  );
}
