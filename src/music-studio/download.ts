import type { Track } from "./model";

export async function downloadTracks(
  tracks: Track[],
  format: "mp3" | "wav" | "flac",
  onProgress: (message: string) => void,
  signal: AbortSignal,
) {
  const { zip, strToU8 } = await import("fflate");
  const files: Record<string, Uint8Array> = {};
  const limit = 256 * 1024 * 1024;
  let bytes = 0;
  for (const [index, track] of tracks.entries()) {
    signal.throwIfAborted();
    onProgress(`Preparing ${index + 1} of ${tracks.length}…`);
    const name = `${String(index + 1).padStart(2, "0")}-${
      track.title
        .replace(/[^a-zA-Z0-9 _-]/g, "")
        .trim()
        .slice(0, 90) || "Untitled"
    }`;
    files[`${name}/settings.json`] = strToU8(
      JSON.stringify(
        {
          title: track.title,
          project: track.project,
          take: track.take,
          form: track.form,
        },
        null,
        2,
      ),
    );
    if (!track.audio && !track.audioUrl) continue;
    if (format === "flac" && !track.source)
      throw new Error(
        "Sample tracks have WAV and MP3 downloads. Choose either format for this selection.",
      );
    const url = !!track.source
      ? `/api/takes/${track.id}/files/audio.${format}`
      : `/media/desert-afterglow-${track.audio}.${format}`;
    const response = await fetch(url, { signal });
    if (!response.ok || !response.body)
      throw new Error(`Could not download “${track.title}”. Please retry.`);
    const reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        bytes += value.length;
        if (bytes > limit) {
          await reader.cancel();
          throw new Error(
            "This download exceeds 256 MB. Select fewer tracks or use MP3.",
          );
        }
        chunks.push(value);
      }
    } finally {
      reader.releaseLock();
    }
    const data = new Uint8Array(size);
    let offset = 0;
    chunks.forEach((chunk) => {
      data.set(chunk, offset);
      offset += chunk.length;
    });
    files[`${name}/audio.${format}`] = data;
  }
  signal.throwIfAborted();
  onProgress("Preparing ZIP…");
  const result = await new Promise<Uint8Array>((resolve, reject) => {
    let cancel = () => {};
    const abort = () => {
      cancel();
      reject(new DOMException("Download cancelled", "AbortError"));
    };
    signal.addEventListener("abort", abort, { once: true });
    cancel = zip(files, { level: 0 }, (error, data) => {
      signal.removeEventListener("abort", abort);
      error ? reject(error) : resolve(data);
    });
  });
  signal.throwIfAborted();
  const url = URL.createObjectURL(
    new Blob([result as Uint8Array<ArrayBuffer>], { type: "application/zip" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `sound-vision-${format}.zip`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
