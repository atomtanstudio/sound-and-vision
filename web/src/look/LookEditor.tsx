import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button, Segmented, Slider } from "../ui/controls";
import { fonts } from "./fonts";
import { LookCanvas, type Part } from "./LookCanvas";
import { ANCHORS, clone, toPct, toPx, type Anchor, type BrandLogo, type FontInfo, type Look, type TextEl } from "./look";
import "./look.css";

const GRID = [{ value: 0, label: "Off" }, { value: 1.25, label: "Fine" }, { value: 2.5, label: "Medium" }, { value: 5, label: "Coarse" }];

/** Lay out the title, the artist and the logos on a picture: drag them on the canvas (they snap to the grid), or set
 *  each exactly on the right: where it's anchored and how many pixels in from the edges, the font, size, spacing,
 *  case and colour. W × H is the size of what's being made (a 3000 px cover, a 1280 × 720 thumbnail). */
export function LookEditor({ picture, infoUrl, W, H, look: initial, title, artist, logos, onSave, onCancel, saving, saveLabel = "Save", extra, words, artistName }: {
  picture: string;
  infoUrl?: string;
  W: number;
  H: number;
  look: Look;
  title: string;
  artist: string;
  logos: BrandLogo[];
  onSave: (look: Look, words: { title: string; artist: string }) => void;
  onCancel?: () => void;
  saving?: boolean;
  saveLabel?: string;
  extra?: ReactNode;
  words?: boolean; // the title and artist can be changed here (a thumbnail's own words)
  /** The artist name itself, typed in the Artist tab (yours on Brand, the song's own in its look). `onCommit` saves it. */
  artistName?: { label: string; note?: string; value: string; placeholder?: string; onChange: (v: string) => void; onCommit: () => void; saving?: boolean };
}) {
  const [look, setLook] = useState<Look>(() => withLogos(clone(initial), logos));
  const [sel, setSel] = useState<Part | null>("title");
  const [grid, setGrid] = useState(() => Number(localStorage.getItem("sv.look.grid") ?? 2.5));
  const [snap, setSnap] = useState(true);
  const [fontList, setFontList] = useState<FontInfo[]>([]);
  const [text, setText] = useState({ title, artist });
  useEffect(() => { if (!words) setText((t) => ({ ...t, title, artist })); }, [title, artist, words]);  // a name typed in place
  useEffect(() => { void fonts().then(setFontList); }, []);
  useEffect(() => {
    try { localStorage.setItem("sv.look.grid", String(grid)); } catch { /* fine */ }
  }, [grid]);
  const set = (fn: (l: Look) => void) => setLook((l) => {
    const n = clone(l);
    fn(n);
    return n;
  });
  const parts: { id: Part; name: string }[] = [
    { id: "title", name: "Title" }, { id: "artist", name: "Artist" },
    ...logos.map((l) => ({ id: `logo:${l.id}` as Part, name: l.name })),
  ];
  return (
    <div className="lk">
      <div className="lk-stage">
        <LookCanvas picture={picture} infoUrl={infoUrl} W={W} H={H} look={look} title={text.title} artist={text.artist} logos={logos} fontList={fontList}
          selected={sel} onSelect={setSel} onChange={setLook} grid={grid} snap={snap} />
        <div className="lk-stagebar">
          <span>Grid</span>
          <Segmented size="sm" label="Grid" value={grid} onChange={setGrid} options={GRID} />
          <label className="lk-check"><input type="checkbox" checked={snap} onChange={(e) => setSnap(e.target.checked)} /> Snap</label>
          <span className="lk-hint">Drag to move · Shift to move freely · arrows nudge 1 px</span>
        </div>
      </div>
      <aside className="lk-side">
        {words && (
          <div className="lk-words">
            <label>Title<input className="in" value={text.title} onChange={(e) => setText({ ...text, title: e.target.value })} /></label>
            <label>Artist<input className="in" value={text.artist} onChange={(e) => setText({ ...text, artist: e.target.value })} /></label>
          </div>
        )}
        <div className="lk-parts" role="tablist">
          {parts.map((p) => (
            <button key={p.id} type="button" role="tab" aria-selected={sel === p.id} className={"lk-part" + (sel === p.id ? " on" : "")}
              onClick={() => setSel(p.id)}>{p.name}</button>
          ))}
        </div>
        {sel === "artist" && artistName && (
          <div className="lk-group lk-name">
            <label>
              <span>{artistName.label}</span>
              <input className="in" value={artistName.value} placeholder={artistName.placeholder} onChange={(e) => artistName.onChange(e.target.value)}
                onBlur={artistName.onCommit} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
            </label>
            {artistName.saving ? <p className="la-note">Saving…</p> : artistName.note && <p className="la-note">{artistName.note}</p>}
          </div>
        )}
        {(sel === "title" || sel === "artist") && (
          <TextControls which={sel} el={look[sel]} W={W} H={H} fontList={fontList} set={(fn) => set((l) => fn(l[sel]))} />
        )}
        {sel?.startsWith("logo:") && look.logos[sel.slice(5)] && (
          <LogoControls el={look.logos[sel.slice(5)]} W={W} H={H} set={(fn) => set((l) => fn(l.logos[sel.slice(5)]))} />
        )}
        <div className="lk-group">
          <h4>Shade behind the words</h4>
          <Segmented size="sm" label="Shade" value={typeof look.scrim === "number" ? "set" : look.scrim}
            onChange={(v) => set((l) => { l.scrim = v === "set" ? 0.4 : v; })}
            options={[{ value: "auto", label: "Auto" }, { value: "none", label: "None" }, { value: "set", label: "Set" }]} />
          {typeof look.scrim === "number" && (
            <Slider label="Strength" value={look.scrim} min={0} max={1} step={0.05} onChange={(v) => set((l) => { l.scrim = v; })}
              format={(v) => `${Math.round(v * 100)}%`} />
          )}
        </div>
        {extra}
        <div className="lk-actions">
          {onCancel && <Button kind="ghost" onClick={onCancel}>Cancel</Button>}
          <Button kind="primary" busy={saving} onClick={() => onSave(look, text)}>{saveLabel}</Button>
        </div>
      </aside>
    </div>
  );
}

/** Every logo has a place in the look (a new one starts in a free corner on the server; this covers any that don't). */
function withLogos(look: Look, logos: BrandLogo[]): Look {
  for (const l of logos) look.logos[l.id] ??= { show: true, anchor: "tr", dx: 2.5, dy: 2.5, size: 10 };
  return look;
}

function AnchorPicker({ value, onChange }: { value: Anchor; onChange: (a: Anchor) => void }) {
  const names: Record<Anchor, string> = { tl: "Top left", tc: "Top centre", tr: "Top right", ml: "Middle left", mc: "Centre",
    mr: "Middle right", bl: "Bottom left", bc: "Bottom centre", br: "Bottom right" };
  return (
    <div className="lk-anchor" role="radiogroup" aria-label="Anchored to">
      {(Object.keys(ANCHORS) as Anchor[]).map((a) => (
        <button key={a} type="button" role="radio" aria-checked={a === value} title={names[a]} aria-label={names[a]}
          className={a === value ? "on" : ""} onClick={() => onChange(a)} />
      ))}
    </div>
  );
}

/** Where it sits: the anchor, and how far in from the edges (in pixels of what's being made). */
function Placement({ anchor, dx, dy, W, H, onAnchor, onMove }: {
  anchor: Anchor; dx: number; dy: number; W: number; H: number; onAnchor: (a: Anchor) => void; onMove: (dx: number, dy: number) => void;
}) {
  const [ax, ay] = ANCHORS[anchor];
  return (
    <div className="lk-place">
      <AnchorPicker value={anchor} onChange={onAnchor} />
      <div className="lk-px">
        <label>{ax === 0.5 ? "From the centre (→)" : ax === 0 ? "From the left" : "From the right"}
          <span><input className="in" type="number" value={toPx(dx, W, H)} onChange={(e) => onMove(toPct(Number(e.target.value), W, H), dy)} /> px</span>
        </label>
        <label>{ay === 0.5 ? "From the centre (↓)" : ay === 0 ? "From the top" : "From the bottom"}
          <span><input className="in" type="number" value={toPx(dy, W, H)} onChange={(e) => onMove(dx, toPct(Number(e.target.value), W, H))} /> px</span>
        </label>
      </div>
    </div>
  );
}

function TextControls({ which, el, W, H, fontList, set }: {
  which: "title" | "artist"; el: TextEl; W: number; H: number; fontList: FontInfo[]; set: (fn: (e: TextEl) => void) => void;
}) {
  const info = fontList.find((f) => f.id === el.font);
  const families = useMemo(() => [...fontList].sort((a, b) => a.family.localeCompare(b.family) || a.style.localeCompare(b.style)), [fontList]);
  const s = Math.min(W, H);
  return (
    <div className="lk-group">
      <label className="lk-check"><input type="checkbox" checked={el.show} onChange={(e) => set((x) => { x.show = e.target.checked; })} />
        Show the {which}</label>
      {el.show && (
        <>
          <Segmented size="sm" label="Placement" value={el.place} onChange={(v) => set((x) => { x.place = v; })}
            options={which === "title"
              ? [{ value: "auto", label: "Auto", hint: "Centred, near the top or the bottom: wherever the picture is calmer" }, { value: "manual", label: "Placed" }]
              : [{ value: "auto", label: "Under the title" }, { value: "manual", label: "Placed" }]} />
          {el.place === "manual" && (
            <Placement anchor={el.anchor} dx={el.dx} dy={el.dy} W={W} H={H}
              onAnchor={(a) => set((x) => { x.anchor = a; x.dx = ANCHORS[a][0] === 0.5 ? 0 : 4; x.dy = ANCHORS[a][1] === 0.5 ? 0 : 4; })}
              onMove={(dx, dy) => set((x) => { x.dx = dx; x.dy = dy; })} />
          )}
          <label className="lk-field">Font
            <select className="in" value={el.font} onChange={(e) => set((x) => { x.font = e.target.value; x.weight = null; })}>
              {families.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.family}{f.weight ? (f.id.endsWith("Italic") ? " · Italic" : "") : f.style && f.style !== "Regular" ? ` · ${f.style}` : ""}
                </option>
              ))}
              {!fontList.some((f) => f.id === el.font) && <option value={el.font}>{el.font}</option>}
            </select>
          </label>
          {info?.weight && (
            <Slider label="Weight" value={el.weight ?? info.weight[2]} min={info.weight[0]} max={info.weight[1]} step={10}
              onChange={(v) => set((x) => { x.weight = v; })} />
          )}
          <Slider label="Size" value={el.size} min={which === "title" ? 1.5 : 0.8} max={which === "title" ? 25 : 10} step={0.1}
            onChange={(v) => set((x) => { x.size = v; })} format={(v) => `${Math.round((v * s) / 100)} px`} />
          <Slider label="Letter spacing" value={el.tracking} min={-0.1} max={1.2} step={0.01}
            onChange={(v) => set((x) => { x.tracking = v; })} format={(v) => `${v.toFixed(2)} em`} />
          {which === "title" && (
            <Slider label="Widest line" value={el.width ?? 82} min={20} max={100} step={1}
              onChange={(v) => set((x) => { x.width = v; })} format={(v) => `${Math.round(v)}%`} />
          )}
          <div className="lk-row">
            <Segmented size="sm" label="Case" value={el.case} onChange={(v) => set((x) => { x.case = v; })}
              options={[{ value: "upper", label: "AA" }, { value: "asis", label: "Aa" }, { value: "lower", label: "aa" }]} />
            <Segmented size="sm" label="Colour" value={el.color === "auto" ? "auto" : "set"}
              onChange={(v) => set((x) => { x.color = v === "auto" ? "auto" : "#f2eee6"; })}
              options={[{ value: "auto", label: "From the picture" }, { value: "set", label: "Colour" }]} />
            {el.color !== "auto" && (
              <input type="color" className="lk-color" value={el.color} aria-label="Colour" onChange={(e) => set((x) => { x.color = e.target.value; })} />
            )}
          </div>
          <div className="lk-row">
            <label className="lk-check"><input type="checkbox" checked={el.shadow} onChange={(e) => set((x) => { x.shadow = e.target.checked; })} /> Soft shadow</label>
            {which === "artist" && (
              <label className="lk-check"><input type="checkbox" checked={el.rules ?? true} onChange={(e) => set((x) => { x.rules = e.target.checked; })} /> Rules either side</label>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function LogoControls({ el, W, H, set }: { el: Look["logos"][string]; W: number; H: number; set: (fn: (e: Look["logos"][string]) => void) => void }) {
  const s = Math.min(W, H);
  return (
    <div className="lk-group">
      <label className="lk-check"><input type="checkbox" checked={el.show} onChange={(e) => set((x) => { x.show = e.target.checked; })} /> Show this logo</label>
      {el.show && (
        <>
          <Placement anchor={el.anchor} dx={el.dx} dy={el.dy} W={W} H={H}
            onAnchor={(a) => set((x) => { x.anchor = a; x.dx = ANCHORS[a][0] === 0.5 ? 0 : 2.5; x.dy = ANCHORS[a][1] === 0.5 ? 0 : 2.5; })}
            onMove={(dx, dy) => set((x) => { x.dx = dx; x.dy = dy; })} />
          <Slider label="Width" value={el.size} min={1} max={60} step={0.25} onChange={(v) => set((x) => { x.size = v; })}
            format={(v) => `${Math.round((v * s) / 100)} px`} />
        </>
      )}
    </div>
  );
}
