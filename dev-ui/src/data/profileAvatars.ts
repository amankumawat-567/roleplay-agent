export interface ProfileAvatarOption {
  id: string;
  label: string;
}

/** The local user's own pickable look (see docs/ARCHITECTURE.md's "Profile
 * page") - reuses the same vendored Draftbit Personas illustrations
 * already used for TTS voice presets (dev-ui/src/data/voices.ts), offered
 * here as "pick your own look" rather than "pick a voice's look." Same
 * art style, no new assets needed; "default" is the original single
 * public/profile-avatar.svg every install already ships. */
export const PROFILE_AVATARS: ProfileAvatarOption[] = [
  { id: "profile-avatar", label: "Default" },
  { id: "ryan", label: "Ryan" },
  { id: "aiden", label: "Aiden" },
  { id: "dylan", label: "Dylan" },
  { id: "serena", label: "Serena" },
  { id: "vivian", label: "Vivian" },
];

export function profileAvatarUrlFor(avatarId: string): string {
  const known = PROFILE_AVATARS.some((a) => a.id === avatarId);
  if (!known || avatarId === "profile-avatar") return "/profile-avatar.svg";
  return `/voice-avatars/${avatarId}.svg`;
}
