import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, Check, Clock, MessageSquare, Send, Settings as SettingsIcon, Sparkles, UserRound } from "lucide-react";
import { api, ApiError } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import { PROFILE_AVATARS, profileAvatarUrlFor } from "../data/profileAvatars";
import { formatLastPlayed, formatPlayedTime } from "../utils/playStats";
import type { ProfileStatsResponse } from "../types";

function StatTile({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="glass-panel flex flex-col gap-2 rounded-2xl p-4">
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-[var(--color-accent)]/20 to-[var(--color-accent-2)]/20 text-[var(--color-accent)]">
        {icon}
      </span>
      <span className="text-2xl font-bold tracking-tight">{value}</span>
      <span className="text-xs text-[var(--color-sub-dim)]">{label}</span>
    </div>
  );
}

/** Identity + stats + recent activity + settings, one destination instead
 * of the three "Settings - coming soon" dead ends this used to be (see
 * docs/ARCHITECTURE.md's "Profile page" - translated from `ref/profile.webp`'s
 * game-profile shape, not copied literally: no XP/levels/trophies, since
 * there's no competition in a single-user companion chat app). */
export function ProfilePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const profile = useAppStore((s) => s.profile);
  const updateProfile = useAppStore((s) => s.updateProfile);

  const [avatarId, setAvatarId] = useState(profile.avatar_id);
  const [displayName, setDisplayName] = useState(profile.display_name ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [data, setData] = useState<ProfileStatsResponse | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);

  useEffect(() => {
    setAvatarId(profile.avatar_id);
    setDisplayName(profile.display_name ?? "");
  }, [profile]);

  useEffect(() => {
    api
      .getProfileStats()
      .then(setData)
      .catch((err) => setStatsError(err instanceof Error ? err.message : "Failed to load stats"));
  }, []);

  // React Router's client-side navigation doesn't trigger the browser's
  // own "scroll to #id on load" behavior the way a real page load would -
  // the three old "Settings - coming soon" buttons link here with
  // `#settings`, so this does that scroll manually.
  useEffect(() => {
    if (location.hash !== "#settings") return;
    document.getElementById("settings")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [location.hash]);

  const dirty = avatarId !== profile.avatar_id || displayName.trim() !== (profile.display_name ?? "");

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await updateProfile({ avatar_id: avatarId, display_name: displayName.trim() || null });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save your profile");
    } finally {
      setSaving(false);
    }
  }

  const greeting = profile.display_name ? `Hello, ${profile.display_name}` : "Your profile";

  return (
    <div className="h-full flex-1 overflow-y-auto px-6 py-10">
      <div className="mx-auto max-w-3xl">
        <div className="animate-fade-up flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[var(--color-sub)] transition-all duration-150 hover:bg-white/[0.06] hover:text-[var(--color-text)] active:scale-90"
          >
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="text-xl font-bold tracking-tight">{greeting}</h1>
            <p className="text-sm text-[var(--color-sub)]">Your identity, stats, and settings for this app.</p>
          </div>
        </div>

        <section className="glass-panel animate-fade-up mt-8 rounded-3xl p-6" style={{ animationDelay: "60ms" }}>
          <h2 className="text-sm font-semibold">Identity</h2>
          <div className="mt-4 flex flex-col gap-5 sm:flex-row sm:items-start">
            <img
              src={profileAvatarUrlFor(avatarId)}
              alt=""
              width={72}
              height={72}
              className="shrink-0 rounded-full ring-2 ring-sky-400/60"
            />
            <div className="flex flex-1 flex-col gap-4">
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wider text-[var(--color-sub-dim)]">Avatar</p>
                <div className="flex flex-wrap gap-2">
                  {PROFILE_AVATARS.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      title={option.label}
                      onClick={() => setAvatarId(option.id)}
                      className={`relative rounded-full ring-2 transition-all duration-150 ${
                        avatarId === option.id ? "ring-[var(--color-accent)]" : "ring-transparent hover:ring-white/20"
                      }`}
                    >
                      <img src={profileAvatarUrlFor(option.id)} alt={option.label} width={44} height={44} className="rounded-full" />
                      {avatarId === option.id && (
                        <span className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--color-accent)] text-white">
                          <Check size={10} />
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium uppercase tracking-wider text-[var(--color-sub-dim)]">
                  Display name
                </span>
                <input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Optional - shown as a greeting here"
                  className="w-full max-w-xs rounded-xl border border-[var(--color-border)] bg-white/[0.03] px-3.5 py-2.5 text-sm outline-none transition-all duration-200 placeholder:text-[var(--color-sub-dim)] focus:border-[var(--color-accent)]/60 focus:bg-white/[0.05]"
                />
              </label>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleSave}
                  disabled={!dirty || saving}
                  className="flex items-center gap-1.5 self-start rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-2)] px-4 py-1.5 text-sm font-medium text-white transition-all duration-200 enabled:hover:scale-105 disabled:cursor-not-allowed disabled:opacity-30"
                >
                  {saving ? "Saving…" : saved ? "Saved" : "Save"}
                </button>
                {error && <p className="text-xs text-rose-400">{error}</p>}
              </div>
            </div>
          </div>
        </section>

        <section className="animate-fade-up mt-8" style={{ animationDelay: "120ms" }}>
          <h2 className="mb-3 text-sm font-semibold">Stats</h2>
          {statsError && <p className="text-sm text-rose-400">{statsError}</p>}
          {!statsError && !data && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="animate-shimmer h-24 rounded-2xl" />
              ))}
            </div>
          )}
          {data && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatTile icon={<Sparkles size={15} />} label="Personas created" value={String(data.stats.persona_count)} />
              <StatTile icon={<MessageSquare size={15} />} label="Sessions" value={String(data.stats.session_count)} />
              <StatTile icon={<Send size={15} />} label="Messages sent" value={String(data.stats.message_count)} />
              <StatTile icon={<Clock size={15} />} label="Time chatting" value={formatPlayedTime(data.stats.played_seconds)} />
            </div>
          )}
        </section>

        <section className="animate-fade-up mt-8" style={{ animationDelay: "180ms" }}>
          <h2 className="mb-3 text-sm font-semibold">Recent activity</h2>
          {data && data.recent_activity.length === 0 && (
            <p className="text-sm text-[var(--color-sub-dim)]">Nothing yet - start a chat or create a persona.</p>
          )}
          {data && data.recent_activity.length > 0 && (
            <div className="glass-panel flex flex-col divide-y divide-[var(--color-border-soft)] rounded-2xl">
              {data.recent_activity.map((item, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/[0.04] text-[var(--color-sub)]">
                    {item.kind === "session" ? <MessageSquare size={14} /> : <Sparkles size={14} />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{item.title}</p>
                    <p className="text-xs text-[var(--color-sub-dim)]">
                      {item.kind === "session" ? "Chat started" : "Persona created"} · {formatLastPlayed(item.created_at)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section id="settings" className="animate-fade-up mt-8 scroll-mt-8" style={{ animationDelay: "240ms" }}>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <SettingsIcon size={14} /> Settings
          </h2>
          <div className="glass-panel flex items-start gap-3 rounded-2xl p-4 text-sm text-[var(--color-sub)]">
            <UserRound size={16} className="mt-0.5 shrink-0 text-[var(--color-sub-dim)]" />
            <p>
              This app is configured through files, not a settings panel - see{" "}
              <code className="rounded bg-white/[0.06] px-1 py-0.5 text-xs">configs/*.yaml</code> and{" "}
              <code className="rounded bg-white/[0.06] px-1 py-0.5 text-xs">.env</code> (see{" "}
              <code className="rounded bg-white/[0.06] px-1 py-0.5 text-xs">docs/development.md</code>). Your
              identity above is the one thing that's actually stored per-account.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
