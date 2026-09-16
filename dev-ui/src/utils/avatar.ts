import { createAvatar } from "@dicebear/core";
import { adventurer } from "@dicebear/collection";

/** A deterministic, algorithmically-generated character avatar per seed -
 * no uploaded art, no AI image generation. Same idea as a GitHub identicon,
 * just illustrated rather than geometric, since these represent roleplay
 * characters rather than user accounts. Swapping the whole app's avatar
 * style later is a one-line change (a different @dicebear/collection style
 * has the exact same createAvatar/seed API). */
export function avatarDataUri(seed: string): string {
  return createAvatar(adventurer, { seed }).toDataUri();
}
