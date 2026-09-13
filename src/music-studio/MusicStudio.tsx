import {
  AccountPanel,
  WritingAssistant,
  SongDescription,
  ReferenceSong,
  CoverButton,
  accountStatus,
  type AccountStatus,
} from "./Assistance";
import { musicApi, type BackendStatus } from "./api";
import { useLibrarySelection } from "./selection";
import { VideoWorkspace } from "../video/VideoWorkspace";
import { MediaLibrary } from "./MediaLibrary";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Home,
  PanelLeftClose,
  PanelLeftOpen,
  Music2,
  Clapperboard,
  LibraryBig,
  Sun,
  Moon,
  Search,
  Grid2X2,
  List,
  ChevronDown,
  ChevronRight,
  Plus,
  Heart,
  MoreHorizontal,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Volume2,
  Download,
  X,
  ArrowUpRight,
  Folder,
  Image as ImageIcon,
  SlidersHorizontal,
  Check,
  FileText,
  AudioLines,
  CircleHelp,
  Pencil,
  WandSparkles,
  ArrowRight,
  SquareCheck,
  Trash2,
  RotateCcw,
  FolderInput,
} from "lucide-react";
import {
  generationRequest,
  initialForm,
  initialTracks,
  uniqueTracks,
  projects,
  readLocal,
  validate,
  writeLocal,
  type Page,
  pageFromPath,
  type Sampling,
  type SongForm,
  type Track,
} from "./model";
const time = (s: number) =>
  `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const projectLabel = (name: string) =>
  name === "Loose tracks" ? "Unsorted" : name;
const playable = (track: Track) =>
  !track.deletedAt && !!(track.audio || track.audioUrl);
const duration = (track: Track) =>
  !playable(track) ? 0 : track.source ? track.duration || 0 : 240;
const takeLabel = (track: Track) =>
  track.source === "imported"
    ? "Imported song"
    : track.source === "yue2"
      ? `Take ${track.take || 1}`
      : `${track.audio === 1 ? "Amber" : "Dusk"} take`;
const media = (track: Track, format = "mp3") =>
  track.source
    ? `/api/takes/${track.id}/files/audio.${format}`
    : `/media/desert-afterglow-${track.audio}.${format}`;
function IconButton({
  label,
  children,
  onClick,
  active = false,
  disabled = false,
}: {
  label: string;
  children: ReactNode;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className={`icon-button ${active ? "is-active" : ""}`}
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
function ThemeSwitch() {
  const [theme, setTheme] = useState(
    document.documentElement.dataset.theme || "dark",
  );
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const follow = () => {
      if (!localStorage.getItem("sv-theme")) {
        const t = media.matches ? "dark" : "light";
        setTheme(t);
        document.documentElement.dataset.theme = t;
      }
    };
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, []);
  function choose(value: string) {
    setTheme(value);
    document.documentElement.dataset.theme = value;
    try {
      localStorage.setItem("sv-theme", value);
    } catch {}
  }
  return (
    <div className="theme-switch" role="radiogroup" aria-label="Appearance">
      {(["light", "dark"] as const).map((value, i) => (
        <button
          key={value}
          aria-label={value === "light" ? "Light" : "Dark"}
          role="radio"
          aria-checked={theme === value}
          tabIndex={theme === value ? 0 : -1}
          onClick={() => choose(value)}
          onKeyDown={(e) => {
            if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
              e.preventDefault();
              const v =
                e.key === "Home"
                  ? "light"
                  : e.key === "End"
                    ? "dark"
                    : theme === "light"
                      ? "dark"
                      : "light";
              choose(v);
              (
                e.currentTarget.parentElement?.children[
                  v === "light" ? 0 : 1
                ] as HTMLElement
              ).focus();
            }
          }}
        >
          {i === 0 ? <Sun size={14} /> : <Moon size={14} />}
          <span>{value === "light" ? "Light" : "Dark"}</span>
        </button>
      ))}
    </div>
  );
}
function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    d.showModal();
    return () => d.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby="modal-title"
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="modal-head">
        <h2 id="modal-title">{title}</h2>
        <IconButton label="Close dialog" onClick={close}>
          <X />
        </IconButton>
      </div>
      {children}
    </dialog>
  );
}
function SamplingFields({
  title,
  value,
  onChange,
}: {
  title: string;
  value: Sampling;
  onChange: (value: Sampling) => void;
}) {
  const fields: [keyof Sampling, string, number, number | undefined, number][] =
    [
      ["temperature", "Temperature", 0, 5, 0.01],
      ["top_p", "Top-p", 0.001, 1, 0.01],
      ["top_k", "Top-k", 1, undefined, 1],
      ["repetition_penalty", "Repetition penalty", 0.001, undefined, 0.001],
      ["penalty_window", "Penalty window", 1, 100, 1],
      ["min_tokens", "Minimum tokens", 0, undefined, 1],
      ["max_tokens", "Maximum tokens", 1, undefined, 1],
    ];
  return (
    <fieldset className="sampling">
      <legend>{title}</legend>
      <div className="field-grid">
        {fields.map(([key, label, min, max, step]) => (
          <label key={key}>
            {label}
            <input
              type="number"
              min={min}
              max={max}
              step={step}
              value={Number.isNaN(value[key]) ? "" : value[key]}
              onChange={(e) =>
                onChange({
                  ...value,
                  [key]: e.target.value === "" ? NaN : Number(e.target.value),
                })
              }
            />
          </label>
        ))}
      </div>
    </fieldset>
  );
}
export function MusicStudio() {
  const [page, setPage] = useState<Page>(() => pageFromPath(location.pathname));
  useEffect(() => {
    document.title = `Sound/Vision — ${page[0].toUpperCase() + page.slice(1)}`;
  }, [page]);
  const [mode, setMode] = useState<"simple" | "advanced">("simple");
  const [writingRequest, setWritingRequest] = useState(0);
  function openWriting(task: string) {
    setForm((current) => ({ ...current, writingTask: task }));
    setWritingRequest((current) => current + 1);
  }
  const [railCollapsed, setRailCollapsed] = useState(() =>
    readLocal("sv-rail-collapsed", false),
  );
  const [compactViewport, setCompactViewport] = useState(
    () => matchMedia("(max-width: 1000px)").matches,
  );
  const [mobileRailOpen, setMobileRailOpen] = useState(false);
  const rail = useRef<HTMLElement>(null);
  const railToggle = useRef<HTMLButtonElement>(null);
  const railExpanded = compactViewport ? mobileRailOpen : !railCollapsed;
  useEffect(() => {
    const media = matchMedia("(max-width: 1000px)");
    const resize = () => {
      setCompactViewport(media.matches);
      setMobileRailOpen(false);
    };
    media.addEventListener("change", resize);
    return () => media.removeEventListener("change", resize);
  }, []);
  useEffect(() => {
    if (!mobileRailOpen) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileRailOpen(false);
        railToggle.current?.focus();
      }
      if (event.key === "Tab") {
        const buttons = Array.from(
          rail.current?.querySelectorAll<HTMLButtonElement>("button") || [],
        ).filter((button) => button.getClientRects().length);
        const first = buttons[0],
          last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [mobileRailOpen]);
  function toggleRail() {
    if (compactViewport) setMobileRailOpen((open) => !open);
    else {
      setRailCollapsed((value) => !value);
      writeLocal("sv-rail-collapsed", !railCollapsed);
    }
  }
  const [mobileView, setMobileView] = useState<"create" | "library">("create");
  const [form, setForm] = useState<SongForm>(() => ({
    ...initialForm,
    ...readLocal<Partial<SongForm>>("sv-form-v2", {}),
  }));
  const [tracks, setTracks] = useState<Track[]>(() =>
    uniqueTracks(readLocal("sv-library-v2", initialTracks)),
  );
  const [backend, setBackend] = useState<BackendStatus | null>(null);
  const backendSeen = useRef(false);
  const libraryRevision = useRef(0);
  const libraryMutating = useRef(false);
  const [account, setAccount] = useState<AccountStatus | null>(null);
  const refreshAccount = () => {
    void accountStatus()
      .then(setAccount)
      .catch(() => setAccount(null));
  };
  useEffect(() => {
    refreshAccount();
    const timer = setInterval(refreshAccount, 4000);
    return () => clearInterval(timer);
  }, []);
  const [submitting, setSubmitting] = useState(false);
  const [planText, setPlanText] = useState<string | null>(null);
  const [originalPlan, setOriginalPlan] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      if (libraryMutating.current) return;
      const revision = libraryRevision.current;
      try {
        const [status, library] = await Promise.all([
          musicApi.health(),
          musicApi.library(),
        ]);
        if (
          disposed ||
          libraryMutating.current ||
          revision !== libraryRevision.current
        )
          return;
        backendSeen.current = true;
        setBackend(status);
        setTracks((previous) =>
          uniqueTracks([
            ...library.tracks,
            ...previous.filter((t) => !t.source),
          ]),
        );
        setDetail((previous) => {
          const fresh = library.tracks.find((t) => t.id === previous?.id);
          return previous && fresh
            ? { ...fresh, title: previous.title, project: previous.project }
            : previous;
        });
      } catch {
        if (!disposed) setBackend(null);
      }
    };
    void refresh();
    const timer = setInterval(refresh, 3000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, []);
  const [view, setView] = useState<"grid" | "list">(() =>
    readLocal("sv-view-v2", "grid"),
  );
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("newest");
  const [genre, setGenre] = useState("all");
  const [project, setProject] = useState("all");
  const [modal, setModal] = useState<
    "account" | "help" | "cover" | "new-project" | null
  >(null);
  const [detail, setDetail] = useState<Track | null>(null);
  useEffect(() => {
    setPlanText(null);
    setOriginalPlan(null);
  }, [detail?.id]);
  const [customProjects, setCustomProjects] = useState<string[]>(() =>
    readLocal("sv-projects-v2", []),
  );
  useEffect(() => {
    if (!backend) return;
    let disposed = false;
    void musicApi
      .projects()
      .then((result) => {
        if (!disposed)
          setCustomProjects((previous) => [
            ...new Set([...previous, ...result.projects.map((p) => p.name)]),
          ]);
      })
      .catch(() => {});
    return () => {
      disposed = true;
    };
  }, [!!backend]);
  const [libraryDialog, setLibraryDialog] = useState<
    "move" | "trash" | "download" | null
  >(null);
  const [libraryBusy, setLibraryBusy] = useState(false);
  const [libraryError, setLibraryError] = useState("");
  const [moveProject, setMoveProject] = useState("Loose tracks");
  const [moveNewProject, setMoveNewProject] = useState("");
  const [downloadFormat, setDownloadFormat] = useState<"mp3" | "wav" | "flac">(
    "mp3",
  );
  const [downloadProgress, setDownloadProgress] = useState("");
  const downloadAbort = useRef<AbortController | null>(null);
  useEffect(() => () => downloadAbort.current?.abort(), []);
  const [newProject, setNewProject] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [lyricsOpen, setLyricsOpen] = useState(false);
  const [current, setCurrent] = useState("amber");
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [volume, setVolume] = useState(0.7);
  const audio = useRef<HTMLAudioElement>(null);
  const shouldPlay = useRef(false);
  const [videoSource, setVideoSource] = useState(() =>
    readLocal("sv-video-source-v1", ""),
  );
  const pendingVideoSeek = useRef<number | null>(null);
  useEffect(() => {
    writeLocal("sv-video-source-v1", videoSource);
  }, [videoSource]);
  function seekVideo(track: Track, seconds: number) {
    if (current === track.id && audio.current && audio.current.readyState > 0) {
      audio.current.currentTime = Math.min(
        seconds,
        audio.current.duration || seconds,
      );
      setProgress(seconds);
    } else {
      audio.current?.pause();
      shouldPlay.current = false;
      pendingVideoSeek.current = seconds;
      setCurrent(track.id);
      setProgress(seconds);
    }
  }
  const active = tracks.find((t) => t.id === current && playable(t)) ||
    tracks.find(playable) || {
      ...initialTracks[0],
      id: "",
      title: "No track selected",
      audio: undefined,
      cover: undefined,
    };
  const allProjects = [
    ...new Set([
      ...projects,
      ...customProjects,
      ...tracks.map((t) => t.project),
    ]),
  ];
  const shown = tracks
    .filter(
      (t) =>
        (filter === "trash" ? !!t.deletedAt : !t.deletedAt) &&
        (project === "all" || t.project === project) &&
        (genre === "all" || (t.form?.genre || "Unspecified") === genre) &&
        (filter === "all" ||
          filter === "trash" ||
          (filter === "ready" && playable(t)) ||
          (filter === "drafts" && !playable(t)) ||
          (filter === "favorites" && t.favorite)) &&
        `${t.title} ${t.subtitle} ${projectLabel(t.project)}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    )
    .sort((a, b) =>
      sort === "title"
        ? a.title.localeCompare(b.title)
        : sort === "genre"
          ? (a.form?.genre || "Unspecified").localeCompare(
              b.form?.genre || "Unspecified",
            ) || a.title.localeCompare(b.title)
          : sort === "oldest"
            ? a.created - b.created
            : b.created - a.created,
    );
  const selection = useLibrarySelection(
    shown.map((t) => t.id),
    [page, query, filter, project, genre].join("|"),
  );
  const selectedTracks = shown.filter((t) => selection.selected.has(t.id));
  const update = <K extends keyof SongForm>(key: K, value: SongForm[K]) =>
    setForm((f) => ({ ...f, [key]: value }));
  const notify = (text: string) => setNotice(text);
  useEffect(() => {
    if (
      !writeLocal("sv-form-v2", form) ||
      !writeLocal("sv-library-v2", tracks) ||
      !writeLocal("sv-projects-v2", customProjects)
    )
      setNotice(
        "Browser storage is full. Download your drafts to keep a copy.",
      );
  }, [form, tracks, customProjects]);
  useEffect(() => {
    writeLocal("sv-view-v2", view);
  }, [view]);
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect(() => {
    const pop = () => setPage(pageFromPath(location.pathname));
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  useEffect(() => {
    audio.current!.volume = volume;
  }, [volume]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        navigate("music");
        setMobileView("library");
        requestAnimationFrame(() =>
          document.getElementById("library-search")?.focus(),
        );
      }
      if (
        e.code === "Space" &&
        !(e.target as HTMLElement).closest(
          "input,textarea,select,button,a,dialog",
        )
      ) {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });
  function navigate(next: Page) {
    setMobileRailOpen(false);
    setPage(next);
    history.pushState({}, "", `/${next}`);
    setError("");
  }
  function toggle() {
    if (!playable(active)) return;
    const a = audio.current!;
    if (a.paused)
      void a.play().catch(() => notify("Playback could not start. Try again."));
    else a.pause();
  }
  function listen(track: Track) {
    pendingVideoSeek.current = null;
    if (!playable(track)) {
      setDetail(track);
      return;
    }
    if (track.id === current) toggle();
    else {
      shouldPlay.current = true;
      setCurrent(track.id);
      setProgress(0);
    }
  }
  function next(offset: number) {
    const ready = tracks.filter(playable);
    const index = ready.findIndex((t) => t.id === current);
    const track = ready[(index + offset + ready.length) % ready.length];
    if (track) {
      shouldPlay.current = playing;
      setCurrent(track.id);
      setProgress(0);
    }
  }
  function favorite(track: Track) {
    if (track.source)
      void musicApi
        .patch(track.id, { favorite: !track.favorite })
        .catch((e) => notify(e.message));
    setTracks((ts) =>
      ts.map((t) => (t.id === track.id ? { ...t, favorite: !t.favorite } : t)),
    );
    if (detail?.id === track.id)
      setDetail({ ...track, favorite: !track.favorite });
  }
  async function create() {
    const issue = validate(form);
    if (issue) {
      setError(issue);
      return;
    }
    setError("");
    if (backendSeen.current && !backend) {
      setError(
        "Music connection lost. Your inputs are saved; reconnect before generating.",
      );
      return;
    }
    if (backend) {
      if (!form.lyrics.trim()) {
        setError(
          "Add lyrics or use the writing assistant, then review and apply its proposal.",
        );
        setLyricsOpen(true);
        requestAnimationFrame(() =>
          Array.from(
            document.querySelectorAll<HTMLTextAreaElement>(".creator textarea"),
          )
            .find(
              (textarea) =>
                textarea.getAttribute("aria-label") === "Your lyrics" ||
                textarea.labels?.[0]?.textContent?.trim() === "Lyrics",
            )
            ?.focus(),
        );
        return;
      }
      if (!backend.generation) {
        setError("YuE2 model files are not ready on the server.");
        return;
      }
      const signature = JSON.stringify(form);
      const pending = readLocal<{ signature: string; id: string } | null>(
        "sv-pending-generation",
        null,
      );
      const id =
        pending?.signature === signature ? pending.id : crypto.randomUUID();
      writeLocal("sv-pending-generation", { signature, id });
      setSubmitting(true);
      try {
        const response = await musicApi.generate(id, form);
        setTracks((previous) => [
          ...response.tracks,
          ...previous.filter(
            (t) => !response.tracks.some((remote) => remote.id === t.id),
          ),
        ]);
        writeLocal("sv-pending-generation", null);
        setQuery("");
        setProject("all");
        setFilter("all");
        setSort("newest");
        setMobileView("library");
        notify(`${form.count === 2 ? "Two takes" : "Song"} queued on Legion.`);
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : "Could not submit the song. Retry uses the same request ID.",
        );
      } finally {
        setSubmitting(false);
      }
      return;
    }
    const requestId = crypto.randomUUID();
    const title =
      form.title.trim() ||
      form.description
        .trim()
        .split(/[.!?\n]/)[0]
        .slice(0, 44) ||
      "Untitled";
    const now = Date.now();
    const added: Track[] = Array.from({ length: form.count }, (_, i) => ({
      id: crypto.randomUUID(),
      title,
      subtitle: `Take ${i + 1} · Awaiting generation`,
      project: form.project,
      favorite: false,
      created: now - i,
      form: structuredClone(form),
      requestId,
      take: i + 1,
      coverStatus: "requested",
    }));
    setTracks((ts) => [...added, ...ts]);
    setQuery("");
    setProject("all");
    setFilter("all");
    setSort("newest");
    setMobileView("library");
    notify(
      `${form.count === 2 ? "Two drafts" : "Draft"} saved. Generation is not connected in this preview.`,
    );
  }
  function exportRequest(track: Track) {
    if (!track.form) return;
    const data = generationRequest(
      { ...track.form, title: track.title, project: track.project },
      track.requestId || track.id,
    );
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `${track.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-request.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function openProject(name: string) {
    setProject(name);
    setQuery("");
    setFilter("all");
    setMobileView("library");
    navigate("music");
  }
  function loadDraft(track: Track) {
    if (track.form)
      setForm({
        ...structuredClone(track.form),
        title: track.title,
        project: track.project,
      });
    setLyricsOpen(!!track.form?.lyrics);
    setDetail(null);
    setMobileView("create");
    navigate("music");
    notify("Draft opened in the creation panel.");
  }
  async function createProject() {
    const name = newProject.trim();
    if (!name) return;
    if (
      allProjects.some(
        (project) =>
          projectLabel(project).toLocaleLowerCase() ===
          name.toLocaleLowerCase(),
      )
    ) {
      notify("A project with that name already exists.");
      return;
    }
    if (backendSeen.current && !backend) {
      notify("Reconnect to create a project on Legion.");
      return;
    }
    try {
      if (backend) await musicApi.createProject(name);
    } catch (error) {
      notify((error as Error).message);
      return;
    }
    setCustomProjects((p) => [...new Set([...p, name])]);
    update("project", name);
    setNewProject("");
    setModal(null);
    openProject(name);
  }
  async function saveDetails() {
    if (!detail) return;
    const patch = {
      title: detail.title.trim() || "Untitled",
      project: detail.project,
    };
    libraryMutating.current = true;
    libraryRevision.current++;
    setLibraryBusy(true);
    setLibraryError("");
    try {
      const saved = detail.source
        ? await musicApi.patch(detail.id, patch)
        : { ...detail, ...patch };
      setTracks((previous) =>
        previous.map((t) => (t.id === saved.id ? saved : t)),
      );
      setDetail(saved);
      notify("Changes saved.");
    } catch (error) {
      setLibraryError((error as Error).message);
    } finally {
      libraryMutating.current = false;
      libraryRevision.current++;
      setLibraryBusy(false);
    }
  }
  function openLibraryAction(action: "move" | "trash" | "download") {
    setLibraryError("");
    setMoveNewProject("");
    setDownloadProgress("");
    setLibraryDialog(action);
  }
  async function applyLibraryAction(action: "move" | "trash" | "restore") {
    if (!selectedTracks.length || libraryMutating.current) return;
    const destination =
      moveProject === "__new__" ? moveNewProject.trim() : moveProject;
    if (action === "move" && !destination) {
      setLibraryError("Enter a project name.");
      return;
    }
    const ids = new Set(selectedTracks.map((t) => t.id));
    const remote = selectedTracks.filter((t) => !!t.source).map((t) => t.id);
    libraryMutating.current = true;
    libraryRevision.current++;
    setLibraryBusy(true);
    setLibraryError("");
    try {
      const result = remote.length
        ? await musicApi.libraryAction(
            remote,
            action,
            action === "move" ? destination : undefined,
          )
        : { tracks: [] };
      const server = new Map(result.tracks.map((t) => [t.id, t]));
      if (action === "move" && !remote.length && backend)
        await musicApi.createProject(destination);
      setTracks((previous) =>
        previous.map((t) =>
          !ids.has(t.id)
            ? t
            : server.get(t.id) || {
                ...t,
                ...(action === "move"
                  ? { project: destination }
                  : { deletedAt: action === "trash" ? Date.now() : null }),
              },
        ),
      );
      if (action === "move")
        setCustomProjects((previous) => [
          ...new Set([...previous, result.tracks[0]?.project || destination]),
        ]);
      if (action === "trash" && ids.has(current)) {
        audio.current?.pause();
        setPlaying(false);
        setCurrent("");
      }
      notify(
        `${ids.size} ${ids.size === 1 ? "item" : "items"} ${action === "trash" ? "moved to Trash. Restore them from the Trash filter." : action === "restore" ? "restored." : `moved to ${projectLabel(result.tracks[0]?.project || destination)}.`}`,
      );
      selection.clear();
      setLibraryDialog(null);
    } catch (error) {
      setLibraryError((error as Error).message);
    } finally {
      libraryMutating.current = false;
      libraryRevision.current++;
      setLibraryBusy(false);
    }
  }
  async function downloadSelection() {
    if (!selectedTracks.length || downloadAbort.current) return;
    const controller = new AbortController();
    downloadAbort.current = controller;
    setLibraryBusy(true);
    setLibraryError("");
    try {
      const { downloadTracks } = await import("./download");
      await downloadTracks(
        selectedTracks,
        downloadFormat,
        setDownloadProgress,
        controller.signal,
      );
      setLibraryDialog(null);
      notify("ZIP download ready.");
    } catch (error) {
      if ((error as Error).name !== "AbortError")
        setLibraryError((error as Error).message);
    } finally {
      setLibraryBusy(false);
      setDownloadProgress("");
      downloadAbort.current = null;
    }
  }
  const card = (track: Track) => (
    <article
      className={`track ${track.id === current ? "selected-track" : ""} ${selection.selected.has(track.id) ? "batch-selected" : ""}`}
      key={track.id}
      data-track={track.id}
    >
      <button
        type="button"
        className="track-check"
        role="checkbox"
        aria-checked={selection.selected.has(track.id)}
        aria-label={`Select ${track.title} ${takeLabel(track)} ${track.id}`}
        onClick={(event) => selection.toggle(track.id, event.shiftKey)}
      >
        <Check size={15} />
      </button>
      <button
        className={`cover ${track.cover ? "" : "cover-pending"}`}
        aria-label={
          playable(track)
            ? `${playing && track.id === current ? "Pause" : "Play"} ${track.title} ${takeLabel(track)}`
            : `Open ${track.title} draft`
        }
        onClick={() =>
          track.deletedAt ? selection.toggle(track.id) : listen(track)
        }
      >
        {track.cover ? (
          <img src={track.cover} alt="" loading="eager" />
        ) : (
          <div className="pending-art">
            <AudioLines size={34} />
            <span>
              {track.source ? "No cover yet" : "Cover after generation"}
            </span>
          </div>
        )}
        <span className="cover-status">
          {playable(track)
            ? time(duration(track))
            : track.source === "yue2"
              ? track.status === "needs-review"
                ? "Review"
                : track.status === "running"
                  ? "Working"
                  : track.status === "failed"
                    ? "Failed"
                    : track.status === "cancelled"
                      ? "Cancelled"
                      : "Queued"
              : "Draft"}
        </span>
        {track.id === current && (
          <span className="track-state">
            <AudioLines size={12} />
            {playing ? "Playing" : "Selected"}
          </span>
        )}
        <span
          className={`cover-play ${playing && track.id === current ? "playing" : ""}`}
        >
          {playable(track) ? (
            playing && track.id === current ? (
              <Pause size={21} fill="currentColor" />
            ) : (
              <Play size={21} fill="currentColor" />
            )
          ) : (
            <Pencil size={20} />
          )}
        </span>
      </button>
      <div className="track-copy">
        <button
          className="track-title"
          onClick={() => {
            if (track.deletedAt) selection.toggle(track.id);
            else {
              setLibraryError("");
              setDetail(track);
            }
          }}
        >
          {track.title}
        </button>
        <p>{track.subtitle}</p>
        {view === "list" && (
          <span className="list-project">{projectLabel(track.project)}</span>
        )}
      </div>
      <div className="track-actions">
        {!track.deletedAt && (
          <>
            <IconButton
              label={`${track.favorite ? "Unfavorite" : "Favorite"} ${track.title} ${track.id}`}
              active={track.favorite}
              onClick={() => favorite(track)}
            >
              <Heart
                size={17}
                fill={track.favorite ? "currentColor" : "none"}
              />
            </IconButton>
            <IconButton
              label={`Options for ${track.title} ${track.id}`}
              onClick={() => {
                setLibraryError("");
                setDetail(track);
              }}
            >
              <MoreHorizontal size={19} />
            </IconButton>
          </>
        )}
      </div>
    </article>
  );
  return (
    <div
      className={`studio page-${page} ${railExpanded ? "rail-expanded" : "rail-collapsed"} ${compactViewport && mobileRailOpen ? "rail-overlay" : ""}`}
    >
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {compactViewport && mobileRailOpen && (
        <button
          className="rail-backdrop"
          tabIndex={-1}
          aria-label="Close navigation"
          onClick={() => {
            setMobileRailOpen(false);
            railToggle.current?.focus();
          }}
        />
      )}
      <aside
        className="primary-rail"
        id="primary-navigation"
        ref={rail}
        aria-label="Navigation"
      >
        <div className="rail-header">
          <button
            className="wordmark"
            onClick={() => navigate("home")}
            aria-label="Sound Vision home"
          >
            <span>
              sound<span className="brand-slash">/</span>
            </span>
            <span>vision</span>
          </button>
          <button
            className="rail-toggle"
            ref={railToggle}
            aria-label={
              railExpanded ? "Collapse navigation" : "Expand navigation"
            }
            title={railExpanded ? "Collapse navigation" : "Expand navigation"}
            aria-expanded={railExpanded}
            aria-controls="primary-navigation"
            onClick={toggleRail}
          >
            {railExpanded ? (
              <PanelLeftClose size={20} />
            ) : (
              <PanelLeftOpen size={20} />
            )}
          </button>
        </div>
        <nav aria-label="Main navigation">
          {(
            [
              { id: "home", label: "Home", icon: Home },
              { id: "music", label: "Music", icon: Music2 },
              { id: "video", label: "Video", icon: Clapperboard },
              { id: "library", label: "Library", icon: LibraryBig },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              aria-label={item.label}
              title={!railExpanded ? item.label : undefined}
              onClick={() => navigate(item.id)}
              aria-current={page === item.id ? "page" : undefined}
            >
              <item.icon size={20} />
              <span>{item.label}</span>
              {page === item.id && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="rail-bottom">
          <button
            aria-label={`Your account, ${account?.connected ? "connected" : "not connected"}`}
            onClick={() => {
              setMobileRailOpen(false);
              setModal("account");
            }}
          >
            <span className="account-icon">
              S<span>/</span>V
            </span>
            <span>
              Your account
              <small>
                {account?.connected ? "Connected" : "Not connected"}
              </small>
            </span>
          </button>
          <button
            className="help-link"
            aria-label="About this preview"
            onClick={() => {
              setMobileRailOpen(false);
              setModal("help");
            }}
          >
            <CircleHelp size={16} />
            <span>About this preview</span>
          </button>
        </div>
      </aside>
      <div className="workspace-body" inert={compactViewport && mobileRailOpen}>
        <header className="topbar">
          <div className="breadcrumb">
            {page[0].toUpperCase() + page.slice(1)}
            <ChevronRight size={14} />
            <span>
              {page === "home"
                ? "Your library"
                : page === "music"
                  ? "Create"
                  : page === "library"
                    ? "Songs and videos"
                    : "New video"}
            </span>
          </div>
          <div className="topbar-right">
            <span className="preview-label">
              <span />
              {backend
                ? "YuE2 connected"
                : backendSeen.current
                  ? "Music offline"
                  : "Interface preview"}
            </span>
            <ThemeSwitch />
          </div>
        </header>
        {page === "music" && (
          <div
            className="mobile-tabs"
            role="tablist"
            aria-label="Music workspace"
          >
            <button
              role="tab"
              aria-selected={mobileView === "create"}
              onClick={() => setMobileView("create")}
            >
              Create
            </button>
            <button
              role="tab"
              aria-selected={mobileView === "library"}
              onClick={() => setMobileView("library")}
            >
              Your music <span>{tracks.length}</span>
            </button>
          </div>
        )}
        <div className={`work-area mobile-${mobileView}`}>
          {page === "music" && (
            <section className="creator" aria-label="Song creation">
              <div className="creator-heading">
                <h1>New song</h1>
                <span className="saved-label">Draft autosaved</span>
              </div>
              <div
                className="mode-switch"
                role="tablist"
                aria-label="Creation mode"
              >
                {(["simple", "advanced"] as const).map((m) => (
                  <button
                    key={m}
                    role="tab"
                    aria-selected={mode === m}
                    tabIndex={mode === m ? 0 : -1}
                    onClick={() => setMode(m)}
                    onKeyDown={(e) => {
                      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
                        e.preventDefault();
                        const next = m === "simple" ? "advanced" : "simple";
                        setMode(next);
                        (
                          e.currentTarget.parentElement?.children[
                            next === "simple" ? 0 : 1
                          ] as HTMLElement
                        ).focus();
                      }
                    }}
                  >
                    {m === "simple" ? "Simple" : "Advanced"}
                  </button>
                ))}
              </div>
              <div
                className="creator-fields"
                role="tabpanel"
                aria-label={`${mode} creation`}
              >
                {mode === "simple" ? (
                  <>
                    <SongDescription
                      form={form}
                      change={setForm}
                      account={account}
                      connect={() => setModal("account")}
                    />
                    <div className="prompt-presets" aria-label="Song ideas">
                      {["Indie folk", "Dream pop", "Late-night jazz"].map(
                        (p) => (
                          <button
                            key={p}
                            onClick={() => {
                              update(
                                "description",
                                form.description
                                  ? `${form.description}, ${p.toLowerCase()}`
                                  : p,
                              );
                              update("style", "");
                            }}
                          >
                            <Plus size={12} />
                            {p}
                          </button>
                        ),
                      )}
                    </div>
                    <WritingAssistant
                      simple
                      openRequest={writingRequest}
                      form={form}
                      change={setForm}
                      account={account}
                      connect={() => setModal("account")}
                    />
                    <div className="lyrics-disclosure">
                      <div className="field-heading">
                        <button
                          className="disclosure-title"
                          aria-expanded={lyricsOpen}
                          onClick={() => setLyricsOpen(!lyricsOpen)}
                        >
                          <FileText size={16} />
                          <span>
                            {form.lyrics
                              ? "Your lyrics"
                              : "Add your own lyrics"}
                          </span>
                          <span className="optional">
                            {backend ? "Required" : "Optional"}
                          </span>
                          {lyricsOpen ? (
                            <ChevronDown size={15} />
                          ) : (
                            <Plus size={15} />
                          )}
                        </button>
                        <button
                          type="button"
                          className="writer-wand"
                          aria-label="Generate lyrics"
                          title="Generate lyrics"
                          onClick={() => openWriting("Draft lyrics")}
                        >
                          <WandSparkles size={16} />
                        </button>
                      </div>
                      {lyricsOpen && (
                        <textarea
                          aria-label="Your lyrics"
                          rows={7}
                          value={form.lyrics}
                          onChange={(e) => update("lyrics", e.target.value)}
                          placeholder={
                            "[Verse]\nStart with a line…\n\n[Chorus]"
                          }
                        />
                      )}
                    </div>
                  </>
                ) : (
                  <div className="advanced-fields">
                    <label>
                      Song title
                      <input
                        value={form.title}
                        onChange={(e) => update("title", e.target.value)}
                        placeholder="Untitled"
                      />
                    </label>
                    <div className="field-heading">
                      <label htmlFor="advanced-style">Style</label>
                      <button
                        type="button"
                        className="writer-wand"
                        aria-label="Refine style"
                        title="Refine style"
                        onClick={() => openWriting("Refine the style")}
                      >
                        <WandSparkles size={16} />
                      </button>
                    </div>
                    <textarea
                      id="advanced-style"
                      rows={3}
                      value={form.style || form.description}
                      onChange={(e) => {
                        update("style", e.target.value);
                        if (!e.target.value) update("description", "");
                      }}
                      placeholder="Genre, instruments, vocal character, language…"
                    />
                    <label>
                      Genre
                      <input
                        value={form.genre || ""}
                        onChange={(e) => update("genre", e.target.value)}
                        placeholder="Indie folk, dream pop…"
                        maxLength={80}
                      />
                    </label>
                    <div className="field-heading">
                      <label htmlFor="advanced-lyrics">Lyrics</label>
                      <button
                        type="button"
                        className="writer-wand"
                        aria-label="Generate lyrics"
                        title="Generate lyrics"
                        onClick={() => openWriting("Draft lyrics")}
                      >
                        <WandSparkles size={16} />
                      </button>
                    </div>
                    <textarea
                      id="advanced-lyrics"
                      rows={4}
                      value={form.lyrics}
                      onChange={(e) => update("lyrics", e.target.value)}
                      placeholder={"[Verse]\n\n[Chorus]"}
                    />
                    <WritingAssistant
                      openRequest={writingRequest}
                      form={form}
                      change={setForm}
                      account={account}
                      connect={() => setModal("account")}
                    />
                    <details className="setting-group">
                      <summary>
                        <Music2 size={15} />
                        <span>Composition</span>
                        <ChevronDown size={15} />
                      </summary>
                      <div className="details-body">
                        <label>
                          Score planning
                          <select
                            value={form.cot}
                            onChange={(e) =>
                              update("cot", e.target.value as SongForm["cot"])
                            }
                          >
                            <option value="full">Melody & chords</option>
                            <option value="melody">Melody only</option>
                            <option value="off">No score plan</option>
                          </select>
                        </label>
                        {form.cot !== "off" && (
                          <>
                            <label className="check-label">
                              <input
                                type="checkbox"
                                checked={form.planFirst}
                                onChange={(e) =>
                                  update("planFirst", e.target.checked)
                                }
                              />
                              Review score before recording
                            </label>
                            <label>
                              ABC score{" "}
                              <span className="optional">Optional</span>
                              <textarea
                                className="mono-input"
                                rows={5}
                                value={form.abc}
                                onChange={(e) => update("abc", e.target.value)}
                                placeholder={"X:1\nT:Untitled\nM:4/4\nK:C"}
                              />
                            </label>
                            {form.abc && (
                              <button
                                type="button"
                                className="secondary-button"
                                onClick={() =>
                                  setForm((current) => ({
                                    ...current,
                                    abc: "",
                                    referenceId: undefined,
                                    sourceTakeId: undefined,
                                  }))
                                }
                              >
                                Clear score
                              </button>
                            )}
                            <p className="field-note">
                              Use Vocal / Ins voices. Changing a score creates a
                              new recording.
                            </p>
                          </>
                        )}
                      </div>
                    </details>
                    <details className="setting-group">
                      <summary>
                        <SlidersHorizontal size={15} />
                        <span>Generation settings</span>
                        <ChevronDown size={15} />
                      </summary>
                      <div className="details-body">
                        <p className="field-note">
                          YuE2 defaults. Leave these as they are unless you need
                          finer control.
                        </p>
                        <label>
                          Seed
                          <input
                            inputMode="numeric"
                            value={form.seed}
                            onChange={(e) => update("seed", e.target.value)}
                            placeholder="Random for each take"
                          />
                        </label>
                        <label>
                          Guidance
                          <input
                            type="number"
                            min="0"
                            max="20"
                            step=".01"
                            value={form.cfg_scale}
                            onChange={(e) =>
                              update("cfg_scale", e.target.value)
                            }
                            placeholder={
                              form.cot === "off"
                                ? "1.01 (default)"
                                : "1.0 (default)"
                            }
                          />
                        </label>
                        <SamplingFields
                          title="Music sampling"
                          value={form.semantic}
                          onChange={(v) => update("semantic", v)}
                        />
                        {form.cot !== "off" && (
                          <SamplingFields
                            title="Score sampling"
                            value={form.score}
                            onChange={(v) => update("score", v)}
                          />
                        )}
                        <label>
                          Synthesis steps
                          <input
                            type="number"
                            min="1"
                            step="1"
                            value={
                              Number.isNaN(form.ode_steps) ? "" : form.ode_steps
                            }
                            onChange={(e) =>
                              update(
                                "ode_steps",
                                e.target.value === ""
                                  ? NaN
                                  : Number(e.target.value),
                              )
                            }
                          />
                        </label>
                      </div>
                    </details>
                  </div>
                )}
                <ReferenceSong form={form} change={setForm} />
              </div>
              <div className="create-footer">
                <div className="take-row">
                  <label>Versions</label>
                  <div
                    className="take-switch"
                    role="group"
                    aria-label="Number of versions"
                  >
                    {([1, 2] as const).map((n) => (
                      <button
                        aria-pressed={form.count === n}
                        key={n}
                        onClick={() => update("count", n)}
                      >
                        {n} {n === 1 ? "take" : "takes"}
                      </button>
                    ))}
                  </div>
                </div>
                <button
                  className="cover-setting"
                  onClick={() => setModal("cover")}
                >
                  <ImageIcon size={15} />
                  <span>
                    {account?.images
                      ? "Cover art included"
                      : "Choose an image provider for cover art"}
                  </span>
                  {backend ? <ChevronRight size={14} /> : <Check size={14} />}
                </button>
                <label className="save-to">
                  <span>
                    <Folder size={14} />
                    Save to project
                  </span>
                  <select
                    aria-label="Save new songs to project"
                    value={form.project}
                    onChange={(e) => update("project", e.target.value)}
                  >
                    {allProjects.map((p) => (
                      <option key={p} value={p}>
                        {projectLabel(p)}
                      </option>
                    ))}
                  </select>
                </label>
                {error && (
                  <p className="form-error" role="alert">
                    {error}
                  </p>
                )}
                <button
                  className="create-button"
                  onClick={create}
                  disabled={submitting}
                >
                  <Music2 size={18} />
                  <span>
                    {submitting
                      ? "Submitting…"
                      : `Create ${form.count === 1 ? "song" : "2 takes"}`}
                  </span>
                  <ArrowRight size={17} />
                </button>
                <p className="preview-note">
                  {backend
                    ? "YuE2 · saved on Legion"
                    : "Preview · creates a saved draft"}
                </p>
              </div>
            </section>
          )}
          <main
            id="main-content"
            tabIndex={-1}
            className={`main-content ${page === "music" ? "music-library" : ""}`}
          >
            {page === "home" ? (
              <>
                <div className="section-heading">
                  <div>
                    <h1>Your library</h1>
                    <p>Projects, tracks, and works in progress.</p>
                  </div>
                  <button
                    className="secondary-button"
                    onClick={() => setModal("new-project")}
                  >
                    <Plus size={16} />
                    New project
                  </button>
                </div>
                <div className="home-section-title">
                  <h2>Projects</h2>
                  <span>{allProjects.length}</span>
                </div>
                <div className="project-grid">
                  {allProjects.map((p) => {
                    const items = tracks.filter(
                      (t) => t.project === p && !t.deletedAt,
                    );
                    return (
                      <button
                        className="project-card"
                        key={p}
                        onClick={() => openProject(p)}
                      >
                        <div className="project-art">
                          {items
                            .slice(0, 2)
                            .map((t) =>
                              t.cover ? (
                                <img key={t.id} src={t.cover} alt="" />
                              ) : null,
                            )}
                          {!items.length && <Folder size={33} />}
                        </div>
                        <div>
                          <strong>{projectLabel(p)}</strong>
                          <span>
                            {items.length}{" "}
                            {items.length === 1 ? "track" : "tracks"}
                          </span>
                        </div>
                        <ChevronRight size={17} />
                      </button>
                    );
                  })}
                </div>
                <div className="home-section-title recent-heading">
                  <h2>Recent music</h2>
                  <button
                    onClick={() => {
                      setProject("all");
                      navigate("music");
                      setMobileView("library");
                    }}
                  >
                    View all
                    <ArrowRight size={15} />
                  </button>
                </div>
                <div className="home-tracks">
                  {tracks.slice(0, 4).map((t) => (
                    <button
                      key={t.id}
                      className="recent-track"
                      onClick={() => (playable(t) ? listen(t) : loadDraft(t))}
                    >
                      {t.cover ? <img src={t.cover} alt="" /> : <AudioLines />}
                      <span>
                        <strong>{t.title}</strong>
                        <small>{t.subtitle}</small>
                      </span>
                      <span>{playable(t) ? time(duration(t)) : "Draft"}</span>
                      {playable(t) ? <Play size={17} /> : <Pencil size={16} />}
                    </button>
                  ))}
                </div>
              </>
            ) : page === "library" ? (
              <MediaLibrary
                tracks={tracks}
                currentId={current}
                playing={playing}
                play={listen}
                pauseMusic={() => audio.current?.pause()}
                openVideo={(takeId, kind, filmId) => {
                  if (takeId) {
                    setVideoSource(takeId);
                    if (kind) {
                      const key = `sv-video-draft-v1:${takeId}`;
                      writeLocal(key, {
                        version: 1,
                        motionVersion: 2,
                        ...readLocal<Record<string, unknown>>(key, {}),
                        kind:
                          kind === "visualizer"
                            ? "visualizer"
                            : kind === "film"
                              ? "directed"
                              : "cinematic",
                      });
                    }
                  }
                  navigate("video");
                  if (filmId)
                    window.history.replaceState(
                      null,
                      "",
                      `/video?film=${encodeURIComponent(filmId)}`,
                    );
                }}
              />
            ) : page === "video" ? (
              <VideoWorkspace
                imported={(track) => {
                  libraryRevision.current++;
                  setTracks((old) => [
                    track,
                    ...old.filter((t) => t.id !== track.id),
                  ]);
                  setVideoSource(track.id);
                }}
                tracks={tracks}
                sourceId={videoSource}
                chooseSource={setVideoSource}
                currentId={current}
                playing={playing}
                progress={progress}
                audioRef={audio}
                play={listen}
                seek={seekVideo}
              />
            ) : (
              <>
                <div className="section-heading library-heading">
                  <div>
                    <div className="eyebrow">LIBRARY</div>
                    <h2>
                      {filter === "trash"
                        ? "Trash"
                        : project === "all"
                          ? "Your music"
                          : projectLabel(project)}
                      <span>{shown.length}</span>
                    </h2>
                  </div>
                  <button
                    className="project-selector"
                    onClick={() => setModal("new-project")}
                    title="New project"
                  >
                    <Folder size={17} />
                    <Plus size={13} />
                  </button>
                </div>
                <div className="library-toolbar">
                  <div className="search-field">
                    <Search size={17} />
                    <input
                      id="library-search"
                      aria-label="Search your music"
                      placeholder="Search your music"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                    {query ? (
                      <IconButton
                        label="Clear search"
                        onClick={() => setQuery("")}
                      >
                        <X size={14} />
                      </IconButton>
                    ) : (
                      <kbd>⌘ K</kbd>
                    )}
                  </div>
                  <button
                    type="button"
                    className="selection-toggle secondary-button"
                    title="Drag across items, or use checkboxes and Shift-click."
                    aria-pressed={selection.enabled}
                    onClick={() =>
                      selection.enabled
                        ? selection.clear()
                        : selection.setEnabled(true)
                    }
                  >
                    <SquareCheck size={16} />
                    <span>{selection.enabled ? "Done" : "Select"}</span>
                  </button>
                  <div
                    className="view-switch"
                    role="group"
                    aria-label="Library view"
                  >
                    <IconButton
                      label="Cover view"
                      active={view === "grid"}
                      onClick={() => setView("grid")}
                    >
                      <Grid2X2 size={17} />
                    </IconButton>
                    <IconButton
                      label="List view"
                      active={view === "list"}
                      onClick={() => setView("list")}
                    >
                      <List size={18} />
                    </IconButton>
                  </div>
                </div>
                <div className="library-filters">
                  <div
                    className="status-filters"
                    role="group"
                    aria-label="Filter music"
                  >
                    {[
                      ["all", "All"],
                      ["ready", "Ready"],
                      ["drafts", "Drafts"],
                      ["favorites", "Favorites"],
                      ["trash", "Trash"],
                    ].map(([v, label]) => (
                      <button
                        key={v}
                        aria-pressed={filter === v}
                        onClick={() => setFilter(v)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <div className="sort-project">
                    <select
                      aria-label="Filter by project"
                      value={project}
                      onChange={(e) => setProject(e.target.value)}
                    >
                      <option value="all">All projects</option>
                      {allProjects.map((p) => (
                        <option key={p} value={p}>
                          {projectLabel(p)}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label="Filter by genre"
                      value={genre}
                      onChange={(e) => setGenre(e.target.value)}
                    >
                      <option value="all">All genres</option>
                      {[
                        ...new Set(
                          tracks.map((t) => t.form?.genre || "Unspecified"),
                        ),
                      ]
                        .sort()
                        .map((g) => (
                          <option key={g}>{g}</option>
                        ))}
                    </select>
                    <select
                      aria-label="Sort music"
                      value={sort}
                      onChange={(e) => setSort(e.target.value)}
                    >
                      <option value="newest">Newest first</option>
                      <option value="oldest">Oldest first</option>
                      <option value="title">Title A–Z</option>
                      <option value="genre">Genre A–Z</option>
                    </select>
                  </div>
                </div>
                {shown.length ? (
                  <div
                    ref={selection.area}
                    className={`tracks tracks-${view} ${selection.enabled ? "selection-mode" : ""}`}
                    tabIndex={0}
                    aria-label="Music items"
                    {...selection.handlers}
                  >
                    {shown.map(card)}
                  </div>
                ) : (
                  <div className="empty-library">
                    <Music2 size={30} />
                    <h3>
                      {query
                        ? "No matching tracks"
                        : filter === "trash"
                          ? "Trash is empty"
                          : "No tracks here yet"}
                    </h3>
                    <p>
                      {filter === "trash"
                        ? "Deleted items appear here. Restore them whenever you need."
                        : query
                          ? "Try another title, style, or project."
                          : "Your next song can start in the creation panel."}
                    </p>
                    {(query || filter !== "all" || project !== "all") && (
                      <button
                        className="secondary-button"
                        onClick={() => {
                          setQuery("");
                          setFilter("all");
                          setProject("all");
                        }}
                      >
                        Clear filters
                      </button>
                    )}
                  </div>
                )}
                {selection.box && (
                  <div
                    className="selection-marquee"
                    style={selection.box}
                    aria-hidden="true"
                  />
                )}
                {selection.enabled && (
                  <div
                    className="selection-dock"
                    role="region"
                    aria-label="Selection actions"
                  >
                    <div className="selection-count" aria-live="polite">
                      {selectedTracks.length} selected
                    </div>
                    <button
                      type="button"
                      onClick={selection.selectAll}
                      disabled={libraryBusy || !shown.length}
                    >
                      {selectedTracks.length === shown.length && shown.length
                        ? "Deselect all"
                        : "Select all"}
                    </button>
                    <div className="selection-divider" />
                    {filter === "trash" ? (
                      <button
                        type="button"
                        onClick={() => void applyLibraryAction("restore")}
                        disabled={!selectedTracks.length || libraryBusy}
                      >
                        <RotateCcw size={17} />
                        Restore
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            setLibraryError("");
                            setDetail(selectedTracks[0]);
                          }}
                          disabled={selectedTracks.length !== 1 || libraryBusy}
                        >
                          <Pencil size={17} />
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => openLibraryAction("move")}
                          disabled={!selectedTracks.length || libraryBusy}
                        >
                          <FolderInput size={17} />
                          Move
                        </button>
                        <button
                          type="button"
                          onClick={() => openLibraryAction("download")}
                          disabled={!selectedTracks.length || libraryBusy}
                        >
                          <Download size={17} />
                          Download
                        </button>
                        <button
                          type="button"
                          className="danger-action"
                          onClick={() => openLibraryAction("trash")}
                          disabled={!selectedTracks.length || libraryBusy}
                        >
                          <Trash2 size={17} />
                          Delete
                        </button>
                      </>
                    )}
                    <IconButton
                      label="Clear selection"
                      onClick={selection.clear}
                      disabled={libraryBusy}
                    >
                      <X size={17} />
                    </IconButton>
                    {libraryError && !libraryDialog && !detail && (
                      <p className="selection-error" role="alert">
                        {libraryError}
                      </p>
                    )}
                  </div>
                )}
                <div className="library-footnote">
                  <span className="tiny-dot" />
                  {backend ? "Music library" : "Sample library"}
                  <span>
                    {tracks.filter(playable).length} playable tracks ·{" "}
                    {tracks.filter((t) => !t.deletedAt && !playable(t)).length}{" "}
                    song drafts
                  </span>
                </div>
              </>
            )}
          </main>
        </div>
      </div>
      <footer
        className="player"
        aria-label="Music player"
        inert={compactViewport && mobileRailOpen}
      >
        <div className="now-playing">
          {active.cover ? (
            <img src={active.cover} alt="" />
          ) : (
            <Music2 size={34} />
          )}
          <div>
            <strong>{active.title}</strong>
            <span>
              {active.id ? takeLabel(active) : "Choose a track to play"}
            </span>
          </div>
          <IconButton
            label="Favorite current track"
            active={active.favorite}
            disabled={!active.id}
            onClick={() => favorite(active)}
          >
            <Heart size={17} fill={active.favorite ? "currentColor" : "none"} />
          </IconButton>
        </div>
        <div className="transport">
          <div className="transport-controls">
            <IconButton label="Previous take" onClick={() => next(-1)}>
              <SkipBack size={17} fill="currentColor" />
            </IconButton>
            <button
              className="play-button"
              disabled={!playable(active)}
              onClick={toggle}
              aria-label={playing ? "Pause playback" : "Play current track"}
            >
              {playing ? (
                <Pause size={17} fill="currentColor" />
              ) : (
                <Play size={17} fill="currentColor" />
              )}
            </button>
            <IconButton label="Next take" onClick={() => next(1)}>
              <SkipForward size={17} fill="currentColor" />
            </IconButton>
          </div>
          <div className="seek-row">
            <span>{time(progress)}</span>
            <input
              type="range"
              min="0"
              max={duration(active)}
              step=".1"
              aria-label="Playback position"
              value={progress}
              onChange={(e) => {
                const t = Number(e.target.value);
                audio.current!.currentTime = t;
                setProgress(t);
              }}
              style={
                {
                  "--progress": `${(progress / (duration(active) || 1)) * 100}%`,
                } as React.CSSProperties
              }
            />
            <span>{time(duration(active))}</span>
          </div>
        </div>
        <div className="player-end">
          <Volume2 size={17} />
          <input
            type="range"
            min="0"
            max="1"
            step=".01"
            aria-label="Volume"
            value={volume}
            onChange={(e) => setVolume(Number(e.target.value))}
          />
          <a
            className="icon-button"
            href={playable(active) ? media(active, "wav") : undefined}
            aria-disabled={!playable(active)}
            download
            aria-label="Download current track WAV"
            title="Download WAV"
          >
            <Download size={18} />
          </a>
        </div>
      </footer>
      <audio
        ref={audio}
        src={playable(active) ? media(active) : undefined}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onTimeUpdate={() => setProgress(audio.current?.currentTime || 0)}
        onLoadedMetadata={() => {
          if (pendingVideoSeek.current !== null && audio.current) {
            audio.current.currentTime = Math.min(
              pendingVideoSeek.current,
              audio.current.duration || pendingVideoSeek.current,
            );
            setProgress(audio.current.currentTime);
            pendingVideoSeek.current = null;
          }
          if (shouldPlay.current) {
            shouldPlay.current = false;
            void audio
              .current!.play()
              .catch(() => notify("Playback could not start."));
          }
        }}
        onEnded={() => setPlaying(false)}
        onError={() =>
          notify(
            !!active.source
              ? "Audio could not load. Check the music connection."
              : "The sample audio could not load.",
          )
        }
      />
      {notice && (
        <div className="toast" role="status">
          <Check size={16} />
          {notice}
        </div>
      )}
      {modal && (
        <Modal
          title={
            modal === "account"
              ? "AI setup"
              : modal === "cover"
                ? "Automatic cover art"
                : modal === "new-project"
                  ? "New project"
                  : "About this preview"
          }
          close={() => setModal(null)}
        >
          {modal === "account" ? (
            <AccountPanel account={account} refresh={refreshAccount} />
          ) : modal === "cover" ? (
            <div className="modal-body">
              <div className="cover-example">
                <img src="/covers/amber.png" alt="Amber sample cover" />
                <img src="/covers/dusk.png" alt="Dusk sample cover" />
              </div>
              <p>One original cover for every take.</p>
              <dl className="metadata">
                <div>
                  <dt>Image model</dt>
                  <dd>
                    {account?.provider === "local"
                      ? "Local ComfyUI workflow"
                      : "OpenAI account image generation"}
                  </dd>
                </div>
                <div>
                  <dt>Versions</dt>
                  <dd>
                    {form.count}{" "}
                    {form.count === 1 ? "take → 1 cover" : "takes → 2 covers"}
                  </dd>
                </div>
                <div>
                  <dt>Direction</dt>
                  <dd>From your song and lyrics</dd>
                </div>
              </dl>
              <p className="field-note">
                {account?.images
                  ? "A separate cover is generated for each new take. You can also create a cover from track details."
                  : "Choose an image provider in AI setup to create cover art."}
              </p>
            </div>
          ) : modal === "new-project" ? (
            <form
              className="modal-body"
              onSubmit={(e) => {
                e.preventDefault();
                createProject();
              }}
            >
              <label>
                Project name
                <input
                  autoFocus
                  maxLength={80}
                  value={newProject}
                  onChange={(e) => setNewProject(e.target.value)}
                  placeholder="Untitled project"
                  required
                />
              </label>
              <button className="create-button" type="submit">
                Create project
                <ArrowRight size={17} />
              </button>
            </form>
          ) : (
            <div className="modal-body">
              <p>
                Sound/Vision is a free, open-source music and video workspace.
              </p>
              <p>
                {backend
                  ? "Generated songs, scores, settings and exports are stored on Legion. Local sample tracks and drafts remain in this browser."
                  : "This preview saves drafts in this browser. The two sample instrumentals are not YuE2 output."}
              </p>
              <p className="field-note">
                {backend
                  ? "Music generation and reference transcription run on Legion. Choose OpenAI or local models in AI setup for writing and cover art. Video rendering is not connected yet."
                  : "OpenAI sign-in, automatic covers and music generation are not connected. Inputs remain saved locally."}
              </p>
            </div>
          )}
        </Modal>
      )}
      {libraryDialog && (
        <Modal
          title={
            libraryDialog === "move"
              ? "Move to project"
              : libraryDialog === "trash"
                ? "Move to Trash?"
                : "Download selected items"
          }
          close={() => {
            if (downloadAbort.current) downloadAbort.current.abort();
            if (!libraryMutating.current) {
              setLibraryDialog(null);
              setLibraryError("");
            }
          }}
        >
          <form
            className="modal-body"
            onSubmit={(event) => {
              event.preventDefault();
              if (libraryDialog === "download") void downloadSelection();
              else void applyLibraryAction(libraryDialog);
            }}
          >
            <p>
              {selectedTracks.length}{" "}
              {selectedTracks.length === 1 ? "item" : "items"} selected.
            </p>
            {libraryDialog === "move" && (
              <>
                <label>
                  Destination
                  <select
                    aria-label="Destination project"
                    value={moveProject}
                    disabled={libraryBusy}
                    onChange={(event) => setMoveProject(event.target.value)}
                  >
                    {allProjects.map((p) => (
                      <option key={p} value={p}>
                        {projectLabel(p)}
                      </option>
                    ))}
                    <option value="__new__">New project…</option>
                  </select>
                </label>
                {moveProject === "__new__" && (
                  <label>
                    Project name
                    <input
                      autoFocus
                      required
                      maxLength={80}
                      value={moveNewProject}
                      onChange={(event) =>
                        setMoveNewProject(event.target.value)
                      }
                      disabled={libraryBusy}
                    />
                  </label>
                )}
              </>
            )}
            {libraryDialog === "trash" && (
              <p>
                Your audio, cover art and generation settings will stay in
                Trash. You can restore these items later.
              </p>
            )}
            {libraryDialog === "download" && (
              <>
                <label>
                  Audio format
                  <select
                    value={downloadFormat}
                    onChange={(event) =>
                      setDownloadFormat(
                        event.target.value as typeof downloadFormat,
                      )
                    }
                    disabled={libraryBusy}
                  >
                    <option value="mp3">MP3 · smaller files</option>
                    <option value="wav">WAV · original quality</option>
                    <option
                      value="flac"
                      disabled={selectedTracks.some((t) => t.audio)}
                    >
                      FLAC · lossless
                    </option>
                  </select>
                </label>
                <p className="field-note">
                  One ZIP with audio and creation settings. Unfinished drafts
                  include settings only. Up to 256 MB per download.
                </p>
              </>
            )}
            {libraryError && (
              <p role="alert" className="form-error">
                {libraryError}
              </p>
            )}
            {downloadProgress && <p role="status">{downloadProgress}</p>}
            <div className="detail-actions">
              <button
                type="button"
                className="secondary-button"
                disabled={libraryMutating.current}
                onClick={() => {
                  downloadAbort.current?.abort();
                  setLibraryDialog(null);
                  setLibraryError("");
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="create-button"
                disabled={libraryBusy || !selectedTracks.length}
              >
                {libraryBusy
                  ? "Working…"
                  : libraryDialog === "move"
                    ? "Move items"
                    : libraryDialog === "trash"
                      ? "Move to Trash"
                      : "Download ZIP"}
              </button>
            </div>
          </form>
        </Modal>
      )}
      {detail && (
        <Modal
          title="Track details"
          close={() => {
            if (libraryBusy) return;
            setDetail(null);
            setPlanText(null);
            setOriginalPlan(null);
          }}
        >
          <div className="modal-body">
            <div className="detail-cover">
              {detail.cover ? (
                <img src={detail.cover} alt="Track cover" />
              ) : (
                <AudioLines size={35} />
              )}
              <div>
                <span className="eyebrow">
                  {detail.source === "imported"
                    ? "IMPORTED SONG"
                    : detail.source === "yue2"
                      ? "YUE2 TAKE"
                      : detail.audio
                        ? "SAMPLE TRACK"
                        : "SONG DRAFT"}
                </span>
                <p>{detail.subtitle}</p>
              </div>
            </div>
            <label>
              Title
              <input
                value={detail.title}
                maxLength={200}
                disabled={libraryBusy}
                onChange={(e) => {
                  const title = e.target.value;
                  setDetail({ ...detail, title });
                }}
              />
            </label>
            <label>
              Project
              <select
                value={detail.project}
                disabled={libraryBusy}
                onChange={(e) => {
                  const project = e.target.value;
                  setDetail({ ...detail, project });
                }}
              >
                {allProjects.map((p) => (
                  <option key={p} value={p}>
                    {projectLabel(p)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="secondary-button"
              disabled={libraryBusy}
              onClick={() => void saveDetails()}
            >
              <Check size={16} />
              {libraryBusy ? "Saving…" : "Save changes"}
            </button>
            {libraryError && (
              <p className="form-error" role="alert">
                {libraryError}
              </p>
            )}
            {detail.source === "yue2" && (
              <>
                {detail.error && (
                  <p className="form-error" role="alert">
                    {detail.error}
                  </p>
                )}
                {detail.warnings?.map((warning) => (
                  <p className="field-note" key={warning}>
                    {warning}
                  </p>
                ))}
                <CoverButton
                  key={detail.id}
                  id={detail.id}
                  connected={!!account?.images}
                  hasCover={!!detail.cover}
                  connect={() => {
                    setDetail(null);
                    setModal("account");
                  }}
                />
                <div className="detail-actions">
                  {[
                    "queued",
                    "waiting-for-resource",
                    "running",
                    "needs-review",
                  ].includes(detail.status || "") && (
                    <button
                      className="secondary-button"
                      onClick={() =>
                        void musicApi
                          .cancel(detail.id)
                          .then(() => notify("Cancellation requested."))
                          .catch((e) => notify(e.message))
                      }
                    >
                      Cancel generation
                    </button>
                  )}
                  {["failed", "cancelled"].includes(detail.status || "") && (
                    <button
                      className="secondary-button"
                      onClick={() =>
                        void musicApi
                          .retry(detail.id)
                          .then(() =>
                            notify(
                              "Take queued for retry; earlier artifacts are retained.",
                            ),
                          )
                          .catch((e) => notify(e.message))
                      }
                    >
                      Retry take
                    </button>
                  )}
                  <button
                    className="secondary-button"
                    onClick={() =>
                      void musicApi
                        .plan(detail.id)
                        .then((result) => {
                          if (!detail.form) return;
                          setForm({
                            ...detail.form,
                            title: detail.title + " edit",
                            abc: result.abc,
                            sourceTakeId: detail.id,
                            writingTask: "Edit score",
                            writingPrompt: "",
                            count: 1,
                            planFirst: false,
                          });
                          setMode("advanced");
                          setPage("music");
                          setDetail(null);
                          notify(
                            "Score loaded. Use the writing assistant to propose an edit, then create a new take.",
                          );
                        })
                        .catch((e) => notify(e.message))
                    }
                  >
                    Edit with assistant
                  </button>
                  <button
                    className="secondary-button"
                    onClick={() =>
                      void musicApi
                        .plan(detail.id)
                        .then((result) => {
                          setPlanText(result.abc);
                          setOriginalPlan(result.abc);
                        })
                        .catch((e) => notify(e.message))
                    }
                  >
                    View score
                  </button>
                  {detail.status === "succeeded" && (
                    <a
                      className="secondary-button"
                      href={`/api/takes/${detail.id}/files/delivery.json`}
                      download
                    >
                      Generation record
                    </a>
                  )}
                </div>
                {planText !== null && (
                  <label>
                    ABC score
                    <textarea
                      rows={8}
                      value={planText}
                      readOnly={detail.status !== "needs-review"}
                      onChange={(e) => setPlanText(e.target.value)}
                    />
                  </label>
                )}
                {detail.status === "needs-review" && (
                  <button
                    className="secondary-button"
                    onClick={() =>
                      void musicApi
                        .continuePlan(
                          detail.id,
                          planText !== null && planText !== originalPlan
                            ? planText
                            : undefined,
                        )
                        .then(() => {
                          setPlanText(null);
                          notify("Score approved. Recording queued.");
                        })
                        .catch((e) => notify(e.message))
                    }
                  >
                    Approve score & generate
                  </button>
                )}
              </>
            )}
            {playable(detail) ? (
              <>
                <p className="field-note">
                  {detail.source === "imported"
                    ? `Imported audio · ${time(duration(detail))} · 48 kHz stereo.`
                    : detail.source === "yue2"
                      ? `YuE2 · ${time(duration(detail))} · 48 kHz stereo.`
                      : "Original sample instrumental · 4:00 · 24 kHz stereo WAV."}
                </p>
                <div className="detail-actions">
                  <a
                    className="secondary-button"
                    href={media(detail, "wav")}
                    download
                  >
                    <Download size={16} />
                    WAV
                  </a>
                  {detail.source && (
                    <a
                      className="secondary-button"
                      href={media(detail, "flac")}
                      download
                    >
                      <Download size={16} />
                      FLAC
                    </a>
                  )}
                  <a className="secondary-button" href={media(detail)} download>
                    <Download size={16} />
                    MP3
                  </a>
                  <button
                    className="secondary-button"
                    onClick={() => {
                      setVideoSource(detail.id);
                      setDetail(null);
                      navigate("video");
                    }}
                  >
                    <Clapperboard size={16} />
                    Make video
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="field-note">
                  {detail.source === "yue2"
                    ? "Generation and its artifacts are saved on Legion."
                    : detail.coverStatus === "reference"
                      ? "Reference cover · audio not generated."
                      : "Audio and cover art are awaiting generation."}
                </p>
                <div className="detail-actions">
                  <button
                    className="secondary-button"
                    onClick={() => loadDraft(detail)}
                  >
                    <Pencil size={16} />
                    Edit draft
                  </button>
                  <button
                    className="secondary-button"
                    onClick={() => exportRequest(detail)}
                  >
                    <Download size={16} />
                    Request JSON
                  </button>
                </div>
              </>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
