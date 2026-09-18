import { Link } from "react-router-dom";
import { profileAvatarUrlFor } from "../data/profileAvatars";
import { useAppStore } from "../stores/useAppStore";

/** The local user's own avatar, shown top-right across pages - same
 * Draftbit Personas illustration style as VoiceAvatar (see its own doc
 * comment for why it's vendored locally rather than called live). A real
 * link to `/profile` now (see docs/ARCHITECTURE.md's "Profile page"), and
 * reflects whichever of `data/profileAvatars.ts`'s curated options the
 * user has actually picked, loaded once into `useAppStore` rather than
 * fetched per instance. Distinct from PersonaAvatar, which represents a
 * roleplay character (seeded per game id) rather than the person using
 * the app. */
export function ProfileAvatar({ size = 36, ringClassName = "ring-sky-400/60" }: { size?: number; ringClassName?: string }) {
  const avatarId = useAppStore((s) => s.profile.avatar_id);
  const label = avatarId === "profile-avatar" ? "Default avatar" : avatarId.charAt(0).toUpperCase() + avatarId.slice(1);
  return (
    <Link to="/profile" aria-label={`View profile (${label})`}>
      <img
        src={profileAvatarUrlFor(avatarId)}
        alt={label}
        width={size}
        height={size}
        className={`shrink-0 rounded-full ring-2 transition-transform duration-150 hover:scale-105 ${ringClassName}`}
        style={{ width: size, height: size }}
        onError={(e) => {
          e.currentTarget.src = "/profile-avatar.svg";
        }}
      />
    </Link>
  );
}
