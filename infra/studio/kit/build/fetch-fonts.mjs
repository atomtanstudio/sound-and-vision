// Build time only (infra/studio/Dockerfile): fetch the open-licensed faces (SIL OFL / Apache) that src/engine/type.js
// knows (FONT_FILES) from the Google Fonts repository into /opt/kit/fonts. Fails the build if any face can't be fetched,
// so a film never meets a missing font. Films don't run this: they have no network, and their fonts/ links here.
//   node build/fetch-fonts.mjs [dir]
import { writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

const BASE = 'https://raw.githubusercontent.com/google/fonts/main/';
export const FONTS = {
  'Anton.ttf': 'ofl/anton/Anton-Regular.ttf',
  'ArchivoBlack.ttf': 'ofl/archivoblack/ArchivoBlack-Regular.ttf',
  'RussoOne.ttf': 'ofl/russoone/RussoOne-Regular.ttf',
  'BebasNeue.ttf': 'ofl/bebasneue/BebasNeue-Regular.ttf',
  'Anybody.ttf': 'ofl/anybody/Anybody[wdth,wght].ttf',
  'Anybody-Italic.ttf': 'ofl/anybody/Anybody-Italic[wdth,wght].ttf',
  'Archivo.ttf': 'ofl/archivo/Archivo[wdth,wght].ttf',
  'Archivo-Italic.ttf': 'ofl/archivo/Archivo-Italic[wdth,wght].ttf',
  'BigShouldersDisplay.ttf': 'ofl/bigshouldersdisplay/BigShouldersDisplay[wght].ttf',
  'LeagueGothic.ttf': 'ofl/leaguegothic/LeagueGothic[wdth].ttf',
  'SixCaps.ttf': 'ofl/sixcaps/SixCaps.ttf',
  'Unbounded.ttf': 'ofl/unbounded/Unbounded[wght].ttf',
  'Syne.ttf': 'ofl/syne/Syne[wght].ttf',
  'RobotoFlex.ttf': 'ofl/robotoflex/RobotoFlex[GRAD,XOPQ,XTRA,YOPQ,YTAS,YTDE,YTFI,YTLC,YTUC,opsz,slnt,wdth,wght].ttf',
  'DelaGothicOne.ttf': 'ofl/delagothicone/DelaGothicOne-Regular.ttf',
  'ClimateCrisis.ttf': 'ofl/climatecrisis/ClimateCrisis[YEAR].ttf',
  'TiltWarp.ttf': 'ofl/tiltwarp/TiltWarp[XROT,YROT].ttf',
  'PlayfairDisplay.ttf': 'ofl/playfairdisplay/PlayfairDisplay[wght].ttf',
  'PlayfairDisplay-Italic.ttf': 'ofl/playfairdisplay/PlayfairDisplay-Italic[wght].ttf',
  'Fraunces.ttf': 'ofl/fraunces/Fraunces[SOFT,WONK,opsz,wght].ttf',
  'Fraunces-Italic.ttf': 'ofl/fraunces/Fraunces-Italic[SOFT,WONK,opsz,wght].ttf',
  'InstrumentSerif.ttf': 'ofl/instrumentserif/InstrumentSerif-Regular.ttf',
  'InstrumentSerif-Italic.ttf': 'ofl/instrumentserif/InstrumentSerif-Italic.ttf',
  'BodoniModa.ttf': 'ofl/bodonimoda/BodoniModa[opsz,wght].ttf',
  'BodoniModa-Italic.ttf': 'ofl/bodonimoda/BodoniModa-Italic[opsz,wght].ttf',
  'Cormorant.ttf': 'ofl/cormorantgaramond/CormorantGaramond[wght].ttf',
  'Cormorant-Italic.ttf': 'ofl/cormorantgaramond/CormorantGaramond-Italic[wght].ttf',
  'DMSerifDisplay.ttf': 'ofl/dmserifdisplay/DMSerifDisplay-Regular.ttf',
  'DMSerifDisplay-Italic.ttf': 'ofl/dmserifdisplay/DMSerifDisplay-Italic.ttf',
  'AbrilFatface.ttf': 'ofl/abrilfatface/AbrilFatface-Regular.ttf',
  'Cinzel.ttf': 'ofl/cinzel/Cinzel[wght].ttf',
  'SpaceMono.ttf': 'ofl/spacemono/SpaceMono-Regular.ttf',
  'SpaceMono-Bold.ttf': 'ofl/spacemono/SpaceMono-Bold.ttf',
  'JetBrainsMono.ttf': 'ofl/jetbrainsmono/JetBrainsMono[wght].ttf',
  'UnifrakturMaguntia.ttf': 'ofl/unifrakturmaguntia/UnifrakturMaguntia-Book.ttf',
  'PirataOne.ttf': 'ofl/pirataone/PirataOne-Regular.ttf',
  'GrenzeGotisch.ttf': 'ofl/grenzegotisch/GrenzeGotisch[wght].ttf',
  'Rye.ttf': 'ofl/rye/Rye-Regular.ttf',
  'Monoton.ttf': 'ofl/monoton/Monoton-Regular.ttf',
  'SpecialElite.ttf': 'apache/specialelite/SpecialElite-Regular.ttf',
  'LibreBarcode39Text.ttf': 'ofl/librebarcode39text/LibreBarcode39Text-Regular.ttf',
  'PermanentMarker.ttf': 'apache/permanentmarker/PermanentMarker-Regular.ttf',
  'RockSalt.ttf': 'apache/rocksalt/RockSalt-Regular.ttf',
  'Handjet.ttf': 'ofl/handjet/Handjet[ELGR,ELSH,wght].ttf',
  'AlfaSlabOne.ttf': 'ofl/alfaslabone/AlfaSlabOne-Regular.ttf',
  'Ultra.ttf': 'apache/ultra/Ultra-Regular.ttf',
  'Shrikhand.ttf': 'ofl/shrikhand/Shrikhand-Regular.ttf',
  'Bungee.ttf': 'ofl/bungee/Bungee-Regular.ttf',
  'Doto.ttf': 'ofl/doto/Doto[ROND,wght].ttf',
  'Oswald.ttf': 'ofl/oswald/Oswald[wght].ttf',
  'BarlowCondensed-Black.ttf': 'ofl/barlowcondensed/BarlowCondensed-Black.ttf',
  'BarlowCondensed-BlackItalic.ttf': 'ofl/barlowcondensed/BarlowCondensed-BlackItalic.ttf',
  'Bricolage.ttf': 'ofl/bricolagegrotesque/BricolageGrotesque[opsz,wdth,wght].ttf',
  'Caveat.ttf': 'ofl/caveat/Caveat[wght].ttf',
  'Silkscreen.ttf': 'ofl/silkscreen/Silkscreen-Regular.ttf',
  'Silkscreen-Bold.ttf': 'ofl/silkscreen/Silkscreen-Bold.ttf',
  'VT323.ttf': 'ofl/vt323/VT323-Regular.ttf',
  'PressStart2P.ttf': 'ofl/pressstart2p/PressStart2P-Regular.ttf',
  'PixelifySans.ttf': 'ofl/pixelifysans/PixelifySans[wght].ttf',
  'Tiny5.ttf': 'ofl/tiny5/Tiny5-Regular.ttf',
  'Jersey10.ttf': 'ofl/jersey10/Jersey10-Regular.ttf',
  'Jersey15.ttf': 'ofl/jersey15/Jersey15-Regular.ttf',
  'DotGothic16.ttf': 'ofl/dotgothic16/DotGothic16-Regular.ttf',
  'OverpassMono.ttf': 'ofl/overpassmono/OverpassMono[wght].ttf',
  'IBMPlexMono-Bold.ttf': 'ofl/ibmplexmono/IBMPlexMono-Bold.ttf',
  'IBMPlexMono-Medium.ttf': 'ofl/ibmplexmono/IBMPlexMono-Medium.ttf',
  'ShareTechMono.ttf': 'ofl/sharetechmono/ShareTechMono-Regular.ttf',
  'MartianMono.ttf': 'ofl/martianmono/MartianMono[wdth,wght].ttf',
  'CourierPrime-Bold.ttf': 'ofl/courierprime/CourierPrime-Bold.ttf',
  'Limelight.ttf': 'ofl/limelight/Limelight-Regular.ttf',
  'PoiretOne.ttf': 'ofl/poiretone/PoiretOne-Regular.ttf',
  'Righteous.ttf': 'ofl/righteous/Righteous-Regular.ttf',
  'Pacifico.ttf': 'ofl/pacifico/Pacifico-Regular.ttf',
  'Yellowtail.ttf': 'apache/yellowtail/Yellowtail-Regular.ttf',
  'Bangers.ttf': 'ofl/bangers/Bangers-Regular.ttf',
  'LuckiestGuy.ttf': 'apache/luckiestguy/LuckiestGuy-Regular.ttf',
  'Fredoka.ttf': 'ofl/fredoka/Fredoka[wdth,wght].ttf',
  'CinzelDecorative-Bold.ttf': 'ofl/cinzeldecorative/CinzelDecorative-Bold.ttf',
  'CinzelDecorative-Black.ttf': 'ofl/cinzeldecorative/CinzelDecorative-Black.ttf',
  'Codystar.ttf': 'ofl/codystar/Codystar-Regular.ttf',
  'StardosStencil-Bold.ttf': 'ofl/stardosstencil/StardosStencil-Bold.ttf',
  'OldStandard-Bold.ttf': 'ofl/oldstandardtt/OldStandard-Bold.ttf',
  'LibreFranklin.ttf': 'ofl/librefranklin/LibreFranklin[wght].ttf',
  'Neonderthaw.ttf': 'ofl/neonderthaw/Neonderthaw-Regular.ttf',
  'TiltNeon.ttf': 'ofl/tiltneon/TiltNeon[XROT,YROT].ttf',
  'RubikMonoOne.ttf': 'ofl/rubikmonoone/RubikMonoOne-Regular.ttf',
  'Staatliches.ttf': 'ofl/staatliches/Staatliches-Regular.ttf',
  'Graduate.ttf': 'ofl/graduate/Graduate-Regular.ttf',
  'Lobster.ttf': 'ofl/lobster/Lobster-Regular.ttf',
};

const dir = resolve(process.argv[2] || new URL('../fonts/', import.meta.url).pathname);
await mkdir(dir, { recursive: true });
const entries = Object.entries(FONTS);
const failed = [];
let next = 0;
async function worker() {
  while (next < entries.length) {
    const [name, path] = entries[next++];
    const url = BASE + path.split('/').map(encodeURIComponent).join('/');
    let ok = false;
    for (let attempt = 1; attempt <= 3 && !ok; attempt++) {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const buf = Buffer.from(await res.arrayBuffer());
        if (buf.length < 1000) throw new Error(`only ${buf.length} bytes`);
        await writeFile(resolve(dir, name), buf);
        ok = true;
      } catch (e) {
        if (attempt === 3) failed.push(`${name} (${path}): ${e.message}`);
        else await new Promise((r) => setTimeout(r, 1500 * attempt));
      }
    }
  }
}
await Promise.all(Array.from({ length: 8 }, worker));
if (failed.length) {
  console.error(`could not fetch ${failed.length} of ${entries.length} fonts:\n  ` + failed.join('\n  '));
  process.exit(1);
}
console.log(`fetched ${entries.length} fonts into ${dir}`);
