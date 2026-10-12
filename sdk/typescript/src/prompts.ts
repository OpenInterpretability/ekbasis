/** Question and state builders, byte for byte the layouts of the Python client (ekbasis.prompts). */
export type Question =
  | { type: "noul"; instructions: string; criteria?: { true?: string; false?: string } }
  | { type: "choice"; instructions: string; criteria: Record<string, string | null> }
  | { type: "score"; instructions: string; criteria: string[] };

export const WORLD_NOTE = "The questions are about the state after all these actions.";

/** A yes/no question. */
export function yesNo(instructions: string): Question {
  return { type: "noul", instructions };
}

/** A question with a fixed set of answers: a list of labels, or label -> short description. */
export function choice(instructions: string, options: string[] | Record<string, string>): Question {
  const criteria: Record<string, string> = Array.isArray(options)
    ? Object.fromEntries(options.map((o) => [String(o), String(o)]))
    : { ...options };
  return { type: "choice", instructions, criteria };
}

export function numbered(lines: string[]): string {
  return lines.map((x, i) => `${i + 1}. ${x}`).join("\n");
}

/** A situation in the world layout: rules, how things stand, what will be done (ekbasis.world_state). */
export function worldState(rules: string, state: string, actions: string[], notes?: string[],
                           notesLabel = "Rules for these actions"): string {
  const acts = numbered(actions) + (notes && notes.length ? `\n\n${notesLabel}: ${notes.join(" ")}` : "");
  return `${rules}\n\nCurrent state:\n${state}\n\nActions, in order:\n${acts}\n\n${WORLD_NOTE}`;
}
