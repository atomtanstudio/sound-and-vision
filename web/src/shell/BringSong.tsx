import { useRef, useState } from "react";
import type { Project } from "../lib/types";
import { go } from "../lib/router";
import { Button, Modal, Segmented, TextArea } from "../ui/controls";
import "./bring.css";
import { machine } from "../lib/machine";

const AUDIO = ".mp3,.wav,.flac,.m4a,.aac,.ogg,.opus,.aif,.aiff,audio/*";

/** Your own finished song (made in Suno, or anywhere) into the library, ready for its videos: the file, and its words
 *  if you have them (otherwise the app hears them). Title, artist and artwork come from the file when it has them. */
export function BringSong({ onClose }: { onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [artist, setArtist] = useState("");
  const [words, setWords] = useState<"hear" | "paste" | "lrc">("hear");
  const [lyrics, setLyrics] = useState("");
  const [lrc, setLrc] = useState<File | null>(null);
  const [cover, setCover] = useState<File | null>(null);
  const [sent, setSent] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const pick = useRef<HTMLInputElement>(null);

  const upload = () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("title", title.trim());
    form.append("artist", artist.trim());
    if (words === "paste") form.append("lyrics", lyrics);
    if (words === "lrc" && lrc) form.append("lrcFile", lrc);
    if (cover) form.append("cover", cover);
    setError(null);
    setSent(0);
    // XHR rather than fetch: a whole song takes a moment to send, and only XHR reports how far it's got
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/songs/upload");
    xhr.upload.onprogress = (e) => e.lengthComputable && setSent(e.loaded / e.total);
    xhr.onload = () => {
      let body: { project?: Project; detail?: string } = {};
      try {
        body = JSON.parse(xhr.responseText);
      } catch { /* not JSON: the message below says so */ }
      if (xhr.status >= 200 && xhr.status < 300 && body.project) {
        onClose();
        go(`/music/${body.project.id}`);
      } else {
        setSent(null);
        setError(body.detail ?? "The song didn't upload. Try again.");
      }
    };
    xhr.onerror = () => {
      setSent(null);
      setError(`That didn't reach ${machine()}. Try again.`);
    };
    xhr.send(form);
  };

  return (
    <Modal title="Bring a song" onClose={onClose}>
      <div className="br">
        <p className="br-lead">A song you made somewhere else, in Suno or anywhere, to make its videos here: a living cover, a
          lyric video or a music video.</p>
        <button type="button" className={"br-drop" + (over ? " over" : "") + (file ? " has" : "")}
          onClick={() => pick.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) setFile(f); }}>
          {file ? <><strong>{file.name}</strong><span>{(file.size / 1e6).toFixed(1)} MB · choose another</span></> :
            <><strong>Drop the song here, or choose it</strong><span>MP3, WAV, FLAC, M4A, OGG · up to 250 MB</span></>}
        </button>
        <input ref={pick} type="file" accept={AUDIO} hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); e.target.value = ""; }} />

        <div className="br-pair">
          <label className="br-field"><span>Title</span>
            <input className="in" value={title} placeholder="From the file, if it has one" onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="br-field"><span>Artist</span>
            <input className="in" value={artist} placeholder="Optional" onChange={(e) => setArtist(e.target.value)} />
          </label>
        </div>

        <div className="br-field">
          <span>The words</span>
          <Segmented size="sm" label="The words" value={words} onChange={setWords} options={[
            { value: "hear", label: "Let the app hear them", hint: "Whisper listens to the vocals; you can correct what it hears" },
            { value: "paste", label: "Paste the lyrics", hint: "Placed on the vocals word by word" },
            { value: "lrc", label: "An LRC file", hint: "Timed lyrics, from Suno's download or a lyrics site" },
          ]} />
          {words === "hear" && <p className="br-note">The app separates the vocals and listens for the words, then times each one.
            An instrumental is fine too.</p>}
          {words === "paste" && <TextArea minRows={4} value={lyrics} placeholder="The lyrics, with [Verse] and [Chorus] if you have them"
            onChange={(e) => setLyrics(e.target.value)} />}
          {words === "lrc" && (
            <label className="br-file">
              <input type="file" accept=".lrc,.txt" onChange={(e) => setLrc(e.target.files?.[0] ?? null)} />
              <span>{lrc ? lrc.name : "Choose the .lrc file"}</span>
            </label>
          )}
        </div>

        <label className="br-file br-cover">
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => setCover(e.target.files?.[0] ?? null)} />
          <span>{cover ? `Cover: ${cover.name}` : "Its cover art (optional: the file's own artwork is used when it has some)"}</span>
        </label>

        {sent !== null && (
          <div className="br-progress"><div className="la-bar"><i style={{ width: `${Math.round(sent * 100)}%` }} /></div>
            <span>{sent < 1 ? `Sending ${Math.round(sent * 100)}%` : "Getting it ready…"}</span></div>
        )}
        {error && <p className="ie-err">{error}</p>}
        <div className="br-go">
          <Button kind="primary" disabled={!file || sent !== null || (words === "lrc" && !lrc)} busy={sent !== null} onClick={upload}>
            Bring it in
          </Button>
          <span className="br-note">Only songs you made or have the rights to.</span>
        </div>
      </div>
    </Modal>
  );
}
