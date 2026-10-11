import { useState } from "react";
import { Wordmark } from "../brand/Wordmark";
import { Button } from "../ui/controls";
import "./pair.css";

/** This browser hasn't been paired with Sound / Vision yet: paste the key once and it's kept. (Devices on the
 *  install's own network, SV_OPEN_NETWORKS, never see this.) */
export function Pair({ keyFile, onPaired }: { keyFile?: string; onPaired: () => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pair() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/pair", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }) });
      if (!r.ok) throw new Error((await r.json()).detail ?? "That didn't work.");
      onPaired();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="pr">
      <div className="pr-card">
        <Wordmark size={30} animate />
        <h1>Pair this browser</h1>
        <p>This browser isn't on the network Sound / Vision is open to, so it needs the key. You do this once per browser.</p>
        <ol>
          <li>
            On the machine Sound / Vision runs on, show the key: <code>cat {keyFile ?? "data/secrets/api-token"}</code>
          </li>
          <li>Paste it here and press Pair.</li>
        </ol>
        <input className="in pr-key" type="password" autoComplete="off" placeholder="Paste the key" value={key}
          onChange={(e) => setKey(e.target.value)} onKeyDown={(e) => e.key === "Enter" && key.trim() && void pair()} />
        {error && <p className="mk-error">{error}</p>}
        <Button kind="primary" size="lg" disabled={!key.trim()} busy={busy} onClick={pair}>Pair</Button>
      </div>
    </main>
  );
}
