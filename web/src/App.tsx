import { useEffect, useState } from "react";
import { usePath } from "./lib/router";
import { Home } from "./shell/Home";
import { LineNotice } from "./shell/LineNotice";
import { Pair } from "./shell/Pair";
import { PlayerBar } from "./shell/PlayerBar";
import { TopBar } from "./shell/TopBar";
import { InfluenceEngine } from "./influence/InfluenceEngine";
import { LibraryPage } from "./library/LibraryPage";
import { SharePage } from "./share/SharePage";
import { MusicIndex } from "./song/MusicIndex";
import { SongPage } from "./song/SongPage";
import { VideoPage } from "./video/VideoPage";
import { VideoStudio } from "./video/VideoStudio";
import { connectEvents } from "./state/events";
import { setMachine } from "./lib/machine";
import { useWho } from "./state/who";

export function App() {
  const path = usePath();
  const [paired, setPaired] = useState<boolean | null>(null);
  const [keyFile, setKeyFile] = useState<string | undefined>();
  useEffect(() => {
    fetch("/api/health").then(async (r) => {
      const body = await r.json().catch(() => ({}));
      if (r.status === 401) setKeyFile(body.keyFile);
      else {
        setMachine(body.machine);
        void useWho.getState().load();  // who does what, for the interface's wording
      }
      setPaired(r.status !== 401);
    }).catch(() => setPaired(true));
  }, []);
  useEffect(() => {
    if (paired) connectEvents();
  }, [paired]);
  if (paired === null) return null;
  if (!paired) return <Pair keyFile={keyFile} onPaired={() => location.reload()} />;
  const song = path.match(/^\/(?:music|song)\/([\w-]+)/);
  const video = path.match(/^\/video\/([\w-]+)/);
  const page = song ? <SongPage key={song[1]} id={song[1]} /> :
    video ? <VideoStudio key={video[1]} id={video[1]} /> :
    path.startsWith("/music") ? <MusicIndex /> :
    path.startsWith("/video") ? <VideoPage /> :
    path.startsWith("/influences") ? <InfluenceEngine /> :
    path.startsWith("/library") ? <LibraryPage /> :
    path.startsWith("/share/brand") || path.startsWith("/brand") ? <SharePage tab="brand" /> :
    path.startsWith("/share") ? <SharePage tab="clips" /> : <Home />;
  return (
    <>
      <TopBar />
      {page}
      <PlayerBar />
      <LineNotice />
    </>
  );
}
