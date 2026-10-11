import { linkTo } from "../lib/router";
import { BrandBody } from "../look/BrandPage";
import { ClipMaker } from "./ClipMaker";
import "../shell/home.css";
import "../song/music-index.css";
import "../library/library.css";
import "../look/look.css";
import "./share.css";

/** Share: getting what you've made out into the world. Clips for TikTok, Reels, Shorts and posts, and your brand (the
 *  logos and the look every cover, thumbnail and clip is set with). */
export function SharePage({ tab }: { tab: "clips" | "brand" }) {
  return (
    <main className="hm mi mi-wide shp">
      <header className="mi-head">
        <div>
          <h1>Share</h1>
          <p>{tab === "clips"
            ? "Clips made for where they're going: the best moment, the right shape, your look, and the sound levelled the way the platforms play it."
            : "Your logos and your house look: how the title, the artist and the logos sit on every cover, living cover, thumbnail and clip."}</p>
        </div>
        <nav className="shp-tabs" aria-label="Share">
          <a className={"shp-tab" + (tab === "clips" ? " on" : "")} aria-current={tab === "clips" ? "page" : undefined} {...linkTo("/share")}>Clips</a>
          <a className={"shp-tab" + (tab === "brand" ? " on" : "")} aria-current={tab === "brand" ? "page" : undefined} {...linkTo("/share/brand")}>Brand</a>
        </nav>
      </header>
      {tab === "clips" ? <ClipMaker /> : <BrandBody />}
    </main>
  );
}
