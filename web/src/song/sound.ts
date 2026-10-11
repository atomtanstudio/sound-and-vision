/** The words offered for a song's sound. Plain names YuE2 understands; anything else can be typed. */
export const GENRES = [
  "pop", "dream pop", "synth pop", "indie rock", "rock", "hip hop", "r&b", "soul", "funk", "disco", "house", "techno",
  "drum and bass", "trip hop", "lo-fi", "ambient", "folk", "country", "jazz", "blues", "metal", "punk", "reggae",
  "latin", "afrobeats", "k-pop", "cinematic", "gospel", "shoegaze", "electropop", "new wave", "trap",
];
export const FIRST_GENRES = 12;

export const MOODS = [
  "uplifting", "wistful", "dreamy", "dark", "melancholy", "euphoric", "romantic", "playful", "hopeful", "tense", "calm",
  "nostalgic", "defiant", "triumphant", "intimate", "angry",
];

export const KEYS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"].flatMap((n) => [`${n} major`, `${n} minor`]);

export const LANGUAGES = [
  { value: "English", label: "English" },
  { value: "Mandarin", label: "Mandarin" },
];

export const SECTION_KINDS = ["intro", "verse", "pre-chorus", "chorus", "post-chorus", "bridge", "hook", "instrumental", "outro"] as const;

/** A short description of the sound for the writer (what the song is meant to sound like). */
export function soundSummary(d: { voice: string | null; genres: string[]; moods: string[]; instruments: string; tempo: number | null }) {
  return [d.voice && d.voice !== "any" ? `${d.voice} vocal` : "", ...d.genres, d.instruments, ...d.moods, d.tempo ? `${d.tempo} BPM` : ""]
    .filter(Boolean)
    .join(", ");
}
