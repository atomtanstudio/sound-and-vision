import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, ApiError, fileUrl } from "../lib/api";
import { go } from "../lib/router";
import { BringSong } from "../shell/BringSong";
import { Button, Segmented } from "../ui/controls";
import { ThumbMaker } from "./ThumbMaker";
import "../shell/home.css";
import "../song/music-index.css";
import "./library.css";
import { machine } from "../lib/machine";

export interface Item {
  key: string;
  type: "song" | "video";
  kind?: "living" | "motion" | "music" | "clip";
  kindName?: string;
  pid: string;
  vid?: string;
  title: string;
  artist: string;
  art?: string | null;
  file?: string;
  thumb?: string;
  shape?: "square" | "wide" | "story";
  aspect: number;
  seconds?: number | null;
  version?: number | null;
  opening?: boolean;
  finish?: boolean;
  custom?: boolean;
  takes?: number;
  ready?: boolean;
  genres?: string[];
  at: number;
  created: number;
  trashedAt?: number;
  part?: { start: number; end: number } | null;
}
interface Folder { id: string; name: string }
interface Lib { folders: Folder[]; placed: Record<string, string>; items: Item[]; trash?: number }
type Box = { x: number; y: number; w: number; h: number };

type Show = "all" | "song" | "video";
type Sort = "new" | "old" | "az";
const KIND_PARAM: Record<string, string> = { living: "living", motion: "kinetic", music: "music", clip: "clip" };
const len = (d?: number | null) => (d ? `${Math.floor(d / 60)}:${String(Math.round(d % 60)).padStart(2, "0")}` : "");
const remember = <T,>(key: string, fallback: T): T => {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
};
const hrefOf = (it: Item) => it.type === "song" ? `/music/${it.pid}` : it.kind === "clip" ? `/share?song=${it.pid}`
  : it.kind === "living" ? `/video/${it.pid}` : `/video/${it.pid}?kind=${KIND_PARAM[it.kind!]}&v=${it.vid}`;
const many = (n: number, one: string, more = `${one}s`) => `${n} ${n === 1 ? one : more}`;

/** Library: every song and every video made from them, in folders you make. Drag anything onto a folder, or press
 *  Select: drag a box across the covers (⌘-click adds or takes away one) and act on them all from the bar below.
 *  Deleting puts things in the Trash, where they keep everything until they're restored. */
export function LibraryPage() {
  const [lib, setLib] = useState<Lib | null>(null);
  const [trash, setTrash] = useState<Item[] | null>(null);
  const [folder, setFolder] = useState<string>(() => remember("sv.lib.folder", "all"));
  const [show, setShow] = useState<Show>(() => remember("sv.lib.show", "all"));
  const [kinds, setKinds] = useState<string[]>([]);
  const [sort, setSort] = useState<Sort>(() => remember("sv.lib.sort", "new"));
  const [q, setQ] = useState("");
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [box, setBox] = useState<Box | null>(null);
  const [undo, setUndo] = useState<{ keys: string[]; text: string } | null>(null);
  const [bringing, setBringing] = useState(false);
  const [thumbFor, setThumbFor] = useState<Item | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const grid = useRef<HTMLDivElement>(null);
  const drawn = useRef(false);  // a box was just drawn: the click that ends it isn't a click on a tile
  const inTrash = folder === "trash";
  const choosing = selecting || inTrash;

  const load = useCallback(() => api.get<Lib>("/api/library").then(setLib).catch((e) => setError(String(e.message ?? e))), []);
  const loadTrash = useCallback(() => api.get<Item[]>("/api/library/trash").then(setTrash).catch(() => setTrash([])), []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (inTrash) void loadTrash(); }, [inTrash, loadTrash]);
  useEffect(() => {
    try {
      localStorage.setItem("sv.lib.folder", JSON.stringify(folder));
      localStorage.setItem("sv.lib.show", JSON.stringify(show));
      localStorage.setItem("sv.lib.sort", JSON.stringify(sort));
    } catch { /* fine */ }
  }, [folder, show, sort]);
  // a remembered folder that has since gone: back to Everything
  useEffect(() => {
    if (lib && !["all", "none", "trash"].includes(folder) && !lib.folders.some((f) => f.id === folder)) setFolder("all");
  }, [lib, folder]);
  useEffect(() => setPicked(new Set()), [folder]);
  useEffect(() => {
    if (!undo) return;
    const t = window.setTimeout(() => setUndo(null), 12000);
    return () => window.clearTimeout(t);
  }, [undo]);

  const act = async (fn: () => Promise<Partial<Lib>>) => {
    setError(null);
    try {
      const r = await fn();
      setLib((l) => (l ? { ...l, ...r } : l));
      return r;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
      return null;
    }
  };
  const move = (keys: string[], to: string | null) => act(() => api.post<Partial<Lib>>("/api/library/move", { keys, folder: to }))
    .then(() => setPicked(new Set()));
  const newFolderWith = async (name: string, keys: string[]) => {
    const before = new Set((lib?.folders ?? []).map((f) => f.id));
    const r = await act(() => api.post<Partial<Lib>>("/api/library/folders", { name }));
    const made = r?.folders?.find((f) => !before.has(f.id));
    if (made && keys.length) await move(keys, made.id);
  };
  const toTrash = async (keys: string[]) => {
    setError(null);
    try {
      const r = await api.post<{ trashed: number; busy: string[] }>("/api/library/trash", { keys });
      const gone = keys.filter((k) => !r.busy.includes(k));
      setPicked(new Set());
      setUndo({
        keys: gone,
        text: `${many(r.trashed, "item")} moved to the Trash.${r.busy.length ? ` ${many(r.busy.length, "song is", "songs are")} being worked on, so stayed.` : ""}`,
      });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    }
  };
  const restore = async (keys: string[]) => {
    setError(null);
    try {
      await api.post("/api/library/restore", { keys });
      setPicked(new Set());
      setUndo(null);
      await Promise.all([load(), inTrash ? loadTrash() : Promise.resolve()]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    }
  };

  const items = useMemo(() => {
    const words = q.trim().toLowerCase();
    const from = inTrash ? trash ?? [] : lib?.items.filter((it) =>
      folder === "all" || (folder === "none" ? !lib.placed[it.key] : lib.placed[it.key] === folder)) ?? [];
    const out = from.filter((it) =>
      (show === "all" || it.type === show) &&
      (!kinds.length || (it.type === "video" && kinds.includes(it.kind!))) &&
      (!words || `${it.title} ${it.artist} ${it.kindName ?? "song"} ${(it.genres ?? []).join(" ")}`.toLowerCase().includes(words)));
    if (!inTrash) out.sort((a, b) => sort === "az" ? a.title.localeCompare(b.title) || b.at - a.at : sort === "old" ? a.created - b.created : b.at - a.at);
    return out;
  }, [lib, trash, inTrash, folder, show, kinds, sort, q]);
  const count = (fid: string) => (lib ? lib.items.filter((it) => (fid === "none" ? !lib.placed[it.key] : lib.placed[it.key] === fid)).length : 0);
  const folders = lib?.folders ?? [];
  const here = inTrash ? "Trash" : folder === "all" ? "Everything" : folder === "none" ? "Not in a folder" : folders.find((f) => f.id === folder)?.name ?? "Everything";
  const chosen = items.filter((it) => picked.has(it.key));

  const toggle = (key: string) => setPicked((s) => {
    const n = new Set(s);
    if (n.has(key)) n.delete(key); else n.add(key);
    return n;
  });
  const stopChoosing = () => { setSelecting(false); setPicked(new Set()); };

  // Escape: let go of the selection, then leave Select; ⌘A: everything in view
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.closest?.("input, textarea, select, [contenteditable]");
      if (e.key === "Escape" && !typing) {
        if (picked.size) setPicked(new Set());
        else if (selecting) setSelecting(false);
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "a" && choosing && !typing) {
        e.preventDefault();
        setPicked(new Set(items.map((it) => it.key)));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [picked, selecting, choosing, items]);

  // Drawing a box across the covers picks every tile it touches (with ⌘, Ctrl or Shift held: adds to what's picked).
  // Near the top or bottom of the window the page scrolls, so a box can reach past what's on screen.
  const startBox = (e: React.PointerEvent) => {
    if (!choosing || e.button !== 0) return;
    const target = e.target as HTMLElement;
    if (target.closest("button, input, select, textarea, label, .lib-menu, .lib-bar")) return;
    const blank = !target.closest("[data-key]");
    const d = { x: e.pageX, y: e.pageY, cx: e.clientX, cy: e.clientY, add: e.metaKey || e.ctrlKey || e.shiftKey, base: new Set(picked), moved: false };
    drawn.current = false;
    const hits = (b: Box) => {
      const out: string[] = [];
      grid.current?.querySelectorAll<HTMLElement>("[data-key]").forEach((el) => {
        const r = el.getBoundingClientRect();
        const left = r.left + window.scrollX, top = r.top + window.scrollY;
        if (left < b.x + b.w && left + r.width > b.x && top < b.y + b.h && top + r.height > b.y) out.push(el.dataset.key!);
      });
      return out;
    };
    const update = () => {
      const px = d.cx + window.scrollX, py = d.cy + window.scrollY;
      const b = { x: Math.min(d.x, px), y: Math.min(d.y, py), w: Math.abs(px - d.x), h: Math.abs(py - d.y) };
      if (!d.moved && b.w < 6 && b.h < 6) return;
      d.moved = true;
      setBox(b);
      const inBox = hits(b);
      setPicked(new Set(d.add ? [...d.base, ...inBox] : inBox));
    };
    let raf = 0;
    const tick = () => {
      const dy = d.cy < 70 ? -16 : d.cy > window.innerHeight - 70 ? 16 : 0;
      if (dy && d.moved) {
        window.scrollBy(0, dy);
        update();
      }
      raf = requestAnimationFrame(tick);
    };
    const onMove = (ev: PointerEvent) => {
      d.cx = ev.clientX;
      d.cy = ev.clientY;
      update();
    };
    const onUp = () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      setBox(null);
      if (d.moved) drawn.current = true;
      else if (blank && !d.add) setPicked(new Set());  // a click on empty space lets go of everything
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    raf = requestAnimationFrame(tick);
  };

  const tileClick = (it: Item, e: React.MouseEvent) => {
    if (e.button !== 0) return;
    if (choosing) {
      e.preventDefault();
      if (drawn.current) { drawn.current = false; return; }
      toggle(it.key);
    } else if (e.metaKey || e.ctrlKey) {  // ⌘-click: start picking, from this one
      e.preventDefault();
      setSelecting(true);
      toggle(it.key);
    } else if (!e.shiftKey) {
      e.preventDefault();
      go(hrefOf(it));
    }
  };

  const dropProps = (fid: string | null, id: string) => ({
    onDragOver: (e: React.DragEvent) => {
      if (e.dataTransfer.types.includes("application/x-sv-items")) {
        e.preventDefault();
        setOver(id);
      }
    },
    onDragLeave: () => setOver((o) => (o === id ? null : o)),
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      setOver(null);
      const keys = JSON.parse(e.dataTransfer.getData("application/x-sv-items") || "[]") as string[];
      if (!keys.length) return;
      if (id === "trash") void toTrash(keys);
      else void move(keys, fid);
    },
  });

  return (
    <main className="lib">
      <aside className="lib-side" aria-label="Folders">
        <h1>Library</h1>
        <nav className="lib-folders">
          <FolderRow icon="all" name="Everything" n={lib?.items.length ?? 0} on={folder === "all"} over={over === "all"} onOpen={() => setFolder("all")}
            {...dropProps(null, "all")} />
          <FolderRow icon="loose" name="Not in a folder" n={count("none")} on={folder === "none"} over={over === "none"} onOpen={() => setFolder("none")}
            {...dropProps(null, "none")} />
          {folders.length > 0 && <span className="lib-folders-h">Your folders</span>}
          {folders.map((f) => (
            <FolderRow key={f.id} icon="folder" name={f.name} n={count(f.id)} on={folder === f.id} over={over === f.id} mine
              onOpen={() => setFolder(f.id)} {...dropProps(f.id, f.id)}
              onRename={(name) => act(() => api.patch(`/api/library/folders/${f.id}`, { name }))}
              onRemove={() => {
                if (confirm(`Delete the folder “${f.name}”? What's in it stays in your Library.`)) {
                  if (folder === f.id) setFolder("all");
                  void act(() => api.del(`/api/library/folders/${f.id}`));
                }
              }} />
          ))}
          <NewFolder onMake={(name) => void act(() => api.post("/api/library/folders", { name }))} />
          <span className="lib-folders-gap" />
          <FolderRow icon="trash" name="Trash" n={lib?.trash ?? 0} on={inTrash} over={over === "trash"} onOpen={() => setFolder("trash")}
            {...dropProps(null, "trash")} />
        </nav>
        <p className="lib-tip">Drag songs and videos onto a folder to file them, or press Select to work on many at once.</p>
      </aside>

      <section className={"lib-main" + (choosing ? " choosing" : "")} onPointerDown={startBox}>
        <header className="lib-head">
          <div>
            <h2>{here}</h2>
            <p>{inTrash ? "Everything here keeps what it had. Restore puts it back, in its folder." : many(items.length, "item")}</p>
          </div>
          <div className="lib-tools">
            <input className="in lib-search" type="search" placeholder="Search titles, artists, kinds…" value={q} onChange={(e) => setQ(e.target.value)} />
            <Segmented size="sm" label="Show" value={show} onChange={(v) => { setShow(v); if (v === "song") setKinds([]); }}
              options={[{ value: "all", label: "All" }, { value: "song", label: "Songs" }, { value: "video", label: "Videos" }]} />
            {!inTrash && (
              <select className="in lib-sort" value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort">
                <option value="new">Newest first</option>
                <option value="old">Oldest first</option>
                <option value="az">A to Z</option>
              </select>
            )}
            {!inTrash && (
              <Button kind={selecting ? "primary" : "plain"} onClick={() => (selecting ? stopChoosing() : setSelecting(true))}
                title={selecting ? "Done selecting (Esc)" : "Pick several, to move or delete them together"}>{selecting ? "Done" : "Select"}</Button>
            )}
            {!inTrash && <Button onClick={() => setBringing(true)} title="A song you made in Suno or anywhere else">Bring a song</Button>}
          </div>
        </header>
        {show !== "song" && (
          <div className="lib-kinds" role="group" aria-label="Kinds of video">
            {[["living", "Living Album Cover"], ["motion", "Motion Graphics"], ["music", "Music Video"], ["clip", "Clips"]].map(([k, name]) => (
              <button key={k} type="button" className={"lib-kind" + (kinds.includes(k) ? " on" : "")} aria-pressed={kinds.includes(k)}
                onClick={() => setKinds((ks) => (ks.includes(k) ? ks.filter((x) => x !== k) : [...ks, k]))}>{name}</button>
            ))}
          </div>
        )}
        {error && <p className="ie-err">{error}</p>}
        {bringing && <BringSong onClose={() => setBringing(false)} />}
        <div ref={grid}>
          {!lib || (inTrash && !trash) ? <p className="mi-soon">Opening your Library…</p> : items.length === 0 ? (
            <div className="hm-empty">{inTrash ? "The Trash is empty." : lib.items.length ? "Nothing here matches." : "No songs or videos yet. Make a song, or bring one in."}</div>
          ) : (
            <Masonry items={items} render={(it) => (
              <Tile key={it.key} it={it} picked={picked.has(it.key)} choosing={choosing} trashed={inTrash}
                onClick={(e) => tileClick(it, e)} onCheck={() => { if (!choosing) setSelecting(true); toggle(it.key); }}
                dragKeys={() => (picked.has(it.key) ? [...picked] : [it.key])}
                onThumb={() => setThumbFor(it)} onTrash={() => void toTrash([it.key])} onRestore={() => void restore([it.key])} />
            )} />
          )}
        </div>
      </section>

      {box && createPortal(<div className="lib-box" style={{ left: box.x, top: box.y, width: box.w, height: box.h }} />, document.body)}
      {(choosing && (selecting || picked.size > 0)) || undo ? (
        <SelectionBar chosen={chosen} total={items.length} folders={folders} folder={folder} inTrash={inTrash} undo={undo} selecting={selecting}
          onMove={(to) => void move([...picked], to)} onNewFolder={(name) => void newFolderWith(name, [...picked])}
          onTrash={() => void toTrash([...picked])} onRestore={() => void restore(picked.size ? [...picked] : undo?.keys ?? [])}
          onAll={() => setPicked(new Set(items.map((it) => it.key)))} onClear={() => setPicked(new Set())}
          onDone={inTrash ? () => setPicked(new Set()) : stopChoosing} onOpenTrash={() => { setUndo(null); setFolder("trash"); }} />
      ) : null}
      {thumbFor && <ThumbMaker item={thumbFor} onClose={() => setThumbFor(null)} onSaved={() => void load()} />}
    </main>
  );
}

/** The bar over the bottom of the page while picking: what's picked, and what can be done with it all at once. */
function SelectionBar({ chosen, total, folders, folder, inTrash, undo, selecting, onMove, onNewFolder, onTrash, onRestore, onAll, onClear, onDone, onOpenTrash }: {
  chosen: Item[]; total: number; folders: Folder[]; folder: string; inTrash: boolean; undo: { keys: string[]; text: string } | null; selecting: boolean;
  onMove: (to: string | null) => void; onNewFolder: (name: string) => void; onTrash: () => void; onRestore: () => void;
  onAll: () => void; onClear: () => void; onDone: () => void; onOpenTrash: () => void;
}) {
  const [menu, setMenu] = useState(false);
  const [naming, setNaming] = useState<string | null>(null);
  const [sure, setSure] = useState(false);
  const n = chosen.length;
  useEffect(() => { setSure(false); }, [n]);
  const videos = chosen.filter((it) => it.type === "video" && it.file);
  const one = n === 1 && chosen[0].kind !== "clip" ? chosen[0] : null;
  const download = () => videos.forEach((it, i) => window.setTimeout(() => {
    const a = document.createElement("a");
    a.href = fileUrl(it.pid, it.file!);
    a.download = `${it.title} (${it.kindName}${it.version ? `, v${it.version}` : ""}).mp4`;
    a.click();
  }, i * 600));

  if (undo && !n) {
    return (
      <div className="lib-bar" role="status">
        <span className="lib-bar-n">{undo.text}</span>
        {undo.keys.length > 0 && <Button size="sm" onClick={onRestore}>Undo</Button>}
        <Button size="sm" kind="ghost" onClick={onOpenTrash}>Open the Trash</Button>
        {selecting && <><span className="lib-bar-gap" /><Button size="sm" kind="ghost" onClick={onDone}>Done</Button></>}
      </div>
    );
  }
  return (
    <div className="lib-bar" role="toolbar" aria-label="What's picked">
      <span className="lib-bar-n">{n ? <><b>{n}</b> selected</> : "Drag across the covers, or click them one at a time. ⌘-click adds or takes one away."}</span>
      {n > 0 && !inTrash && (
        <span className="lib-bar-move">
          <Button size="sm" onClick={() => { setMenu(!menu); setNaming(null); }} aria-expanded={menu}>Move to…</Button>
          {menu && (
            <div className="lib-bar-menu" role="menu">
              {folders.map((f) => (
                <button key={f.id} type="button" role="menuitem" disabled={f.id === folder} onClick={() => { setMenu(false); onMove(f.id); }}>{f.name}</button>
              ))}
              {folders.length > 0 && <hr />}
              {naming === null ? (
                <button type="button" role="menuitem" onClick={() => setNaming("")}>New folder…</button>
              ) : (
                <input className="in" autoFocus placeholder="Folder name, then Enter" value={naming} onChange={(e) => setNaming(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && naming.trim()) { setMenu(false); onNewFolder(naming.trim()); setNaming(null); }
                    if (e.key === "Escape") setNaming(null);
                  }} />
              )}
              <button type="button" role="menuitem" onClick={() => { setMenu(false); onMove(null); }}>Out of its folder</button>
            </div>
          )}
        </span>
      )}
      {one && !inTrash && (
        <Button size="sm" kind="ghost" onClick={() => go(`/share?song=${one.pid}${one.type === "video" ? `&video=${encodeURIComponent(one.key)}` : ""}`)}>Make a clip</Button>
      )}
      {videos.length > 0 && !inTrash && (
        <Button size="sm" kind="ghost" onClick={download} title="Each video downloads as its own file">
          {videos.length === 1 ? "Download" : `Download ${videos.length} videos`}
        </Button>
      )}
      {n > 0 && (inTrash ? (
        <Button size="sm" onClick={onRestore}>Restore</Button>
      ) : sure ? (
        <span className="lib-bar-sure">
          Move {n === 1 ? "it" : `these ${n}`} to the Trash?{chosen.some((it) => it.type === "song") ? " A song takes its videos with it." : ""}
          <Button size="sm" kind="danger" onClick={onTrash}>Move to the Trash</Button>
          <Button size="sm" kind="ghost" onClick={() => setSure(false)}>Cancel</Button>
        </span>
      ) : (
        <Button size="sm" kind="ghost" onClick={() => setSure(true)}>Delete</Button>
      ))}
      <span className="lib-bar-gap" />
      {n < total && <Button size="sm" kind="ghost" onClick={onAll}>Select all</Button>}
      {n > 0 && <Button size="sm" kind="ghost" onClick={onClear}>Clear</Button>}
      {!inTrash && <Button size="sm" kind="ghost" onClick={onDone}>Done</Button>}
    </div>
  );
}

const ICONS: Record<string, React.ReactNode> = {
  all: <path d="M3 5.5h14M3 10h14M3 14.5h14" />,
  loose: <><rect x="3.5" y="3.5" width="5" height="5" rx="1" /><rect x="11.5" y="3.5" width="5" height="5" rx="1" /><rect x="3.5" y="11.5" width="5" height="5" rx="1" /></>,
  folder: <path d="M3 6.2c0-.9.7-1.6 1.6-1.6h3.3l1.6 1.8h5.9c.9 0 1.6.7 1.6 1.6v6.4c0 .9-.7 1.6-1.6 1.6H4.6c-.9 0-1.6-.7-1.6-1.6Z" />,
  trash: <path d="M4 6h12M8 6V4.5h4V6M5.5 6l.8 9.5h7.4l.8-9.5M8.5 8.5v4.5M11.5 8.5v4.5" />,
};

function FolderRow({ icon, name, n, on, over, mine, onOpen, onRename, onRemove, ...drop }: {
  icon: keyof typeof ICONS; name: string; n: number; on: boolean; over: boolean; mine?: boolean; onOpen: () => void;
  onRename?: (name: string) => void; onRemove?: () => void;
} & React.HTMLAttributes<HTMLDivElement>) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(name);
  return (
    <div className={"lib-folder" + (on ? " on" : "") + (over ? " over" : "")} {...drop}>
      {editing ? (
        <input className="in" autoFocus value={text} onChange={(e) => setText(e.target.value)}
          onBlur={() => { setEditing(false); if (text.trim() && text !== name) onRename?.(text); }}
          onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); if (e.key === "Escape") { setText(name); setEditing(false); } }} />
      ) : (
        <button type="button" className="lib-folder-open" onClick={onOpen} onDoubleClick={() => mine && setEditing(true)}>
          <svg className="lib-folder-icon" viewBox="0 0 20 20" aria-hidden="true">{ICONS[icon]}</svg>
          <span className="lib-folder-name">{name}</span>
          <span className="lib-folder-n">{n}</span>
        </button>
      )}
      {mine && !editing && (
        <span className="lib-folder-acts">
          <button type="button" title="Rename" aria-label={`Rename ${name}`} onClick={() => setEditing(true)}>Rename</button>
          <button type="button" title="Delete the folder" aria-label={`Delete ${name}`} onClick={onRemove}>Delete</button>
        </span>
      )}
    </div>
  );
}

function NewFolder({ onMake }: { onMake: (name: string) => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  if (!open) return <button type="button" className="lib-newfolder" onClick={() => setOpen(true)}>+ New folder</button>;
  const done = () => {
    if (name.trim()) onMake(name.trim());
    setName("");
    setOpen(false);
  };
  return (
    <div className="lib-folder">
      <input className="in" autoFocus placeholder="Folder name" value={name} onChange={(e) => setName(e.target.value)}
        onBlur={done} onKeyDown={(e) => { if (e.key === "Enter") done(); if (e.key === "Escape") { setName(""); setOpen(false); } }} />
    </div>
  );
}

/** Columns as wide as the space allows, each tile going to the shortest column so far (shapes kept as they are). */
function Masonry({ items, render }: { items: Item[]; render: (it: Item) => React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const gap = 16;
  const cols = Math.max(1, Math.floor((width + gap) / (250 + gap)));
  const colW = (width - gap * (cols - 1)) / cols;
  const columns: Item[][] = Array.from({ length: cols }, () => []);
  const heights = new Array(cols).fill(0);
  for (const it of items) {
    const c = heights.indexOf(Math.min(...heights));
    columns[c].push(it);
    heights[c] += colW / Math.max(0.3, it.aspect) + 64 + gap;
  }
  return (
    <div className="lib-masonry" ref={ref} style={{ gap }}>
      {columns.map((col, i) => <div key={i} className="lib-col" style={{ gap }}>{col.map(render)}</div>)}
    </div>
  );
}

function Tile({ it, picked, choosing, trashed, onClick, onCheck, dragKeys, onThumb, onTrash, onRestore }: {
  it: Item; picked: boolean; choosing: boolean; trashed: boolean; onClick: (e: React.MouseEvent) => void; onCheck: () => void;
  dragKeys: () => string[]; onThumb: () => void; onTrash: () => void; onRestore: () => void;
}) {
  const [hover, setHover] = useState(false);
  const [menu, setMenu] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const href = hrefOf(it);
  const pic = it.type === "song" ? (it.art ? fileUrl(it.pid, it.art) : null) : it.thumb!;
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    if (hover && !choosing) {
      const t = window.setTimeout(() => { v.currentTime = Math.min(20, (it.seconds ?? 0) * 0.2); void v.play().catch(() => undefined); }, 450);
      return () => window.clearTimeout(t);
    }
    v.pause();
  }, [hover, choosing, it.seconds]);
  const meta = it.type === "song"
    ? [it.ready ? len(it.seconds) : it.takes ? `${it.takes} take${it.takes > 1 ? "s" : ""}` : "No takes yet", it.artist].filter(Boolean).join(" · ")
    : [it.kindName, it.part ? `${len(it.part.start) || "0:00"}–${len(it.part.end)}` : it.opening ? "opening" : it.version ? `v${it.version}` : it.finish ? "with its finish in code" : "", len(it.seconds)].filter(Boolean).join(" · ");
  return (
    <article className={"lib-tile" + (picked ? " picked" : "") + (choosing ? " choosing" : "")} data-key={it.key} draggable={!choosing}
      onDragStart={(e) => {
        e.dataTransfer.setData("application/x-sv-items", JSON.stringify(dragKeys()));
        e.dataTransfer.effectAllowed = "move";
      }}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => { setHover(false); setMenu(false); }}>
      <a className="lib-pic" style={{ aspectRatio: `${it.aspect}` }} href={href} onClick={onClick} draggable={false}>
        {pic ? <img src={pic} alt="" loading="lazy" draggable={false} /> : <span className="lib-noart">{(it.title || "U").slice(0, 1)}</span>}
        {it.type === "video" && it.file && hover && !choosing && (
          <video ref={video} src={fileUrl(it.pid, it.file)} muted playsInline loop preload="none" draggable={false} />
        )}
        <span className={"lib-badge lib-" + (it.kind ?? "song")}>{it.type === "song" ? "Song" : it.kindName}</span>
        {it.seconds ? <span className="lib-len">{len(it.seconds)}</span> : null}
      </a>
      <label className="lib-check" title={picked ? "Picked" : "Pick it"}>
        <input type="checkbox" checked={picked} onChange={onCheck} />
      </label>
      <div className="lib-cap">
        <div>
          <strong>{it.title}</strong>
          <span>{meta}</span>
        </div>
        {!choosing || trashed ? (
          <button type="button" className="lib-more" aria-label="More" aria-expanded={menu} onClick={() => setMenu(!menu)}>
            <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="5" cy="10" r="1.4" /><circle cx="10" cy="10" r="1.4" /><circle cx="15" cy="10" r="1.4" /></svg>
          </button>
        ) : null}
        {menu && (
          <div className="lib-menu" role="menu">
            {trashed ? (
              <button type="button" role="menuitem" onClick={() => { setMenu(false); onRestore(); }}>Restore</button>
            ) : (
              <>
                <button type="button" role="menuitem" onClick={() => go(href)}>Open</button>
                {it.kind !== "clip" && <button type="button" role="menuitem" onClick={() => go(`/share?song=${it.pid}${it.type === "video" ? `&video=${encodeURIComponent(it.key)}` : ""}`)}>Make a clip</button>}
                {it.type === "video" && it.kind !== "clip" && <button type="button" role="menuitem" onClick={() => { setMenu(false); onThumb(); }}>{it.custom ? "Change the thumbnail" : "Make a thumbnail"}</button>}
                {it.type === "video" && it.file && <a role="menuitem" href={fileUrl(it.pid, it.file)} download={`${it.title} (${it.kindName}).mp4`}>Download the video</a>}
                {it.type === "video" && <a role="menuitem" href={it.thumb} download={`${it.title} (${it.kindName}) thumbnail.jpg`}>Download the thumbnail</a>}
                {it.type === "song" && it.art && <a role="menuitem" href={fileUrl(it.pid, it.art.replace(/-sm\.jpg$/, ".jpg"))} download={`${it.title} cover.jpg`}>Download the cover</a>}
                <button type="button" role="menuitem" className="lib-menu-del" onClick={() => { setMenu(false); onTrash(); }}>Move to the Trash</button>
              </>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
