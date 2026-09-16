/** The name shown anywhere the app refers to "who you're talking to" -
 * `character_name` when a persona author has set one, falling back to
 * `title` (the scenario/card display name) for every game.yaml written
 * before that field existed. See docs/ARCHITECTURE.md's "Character name,
 * distinct from the scenario title". */
export function characterNameFor(game: { title: string; character_name: string | null }): string {
  // `||`, not `??` - an empty string (a hand-authored game.yaml's
  // `character_name: ""`, or a cleared editor field) should fall back to
  // title exactly like an unset/null one, not render as blank.
  return game.character_name || game.title;
}
