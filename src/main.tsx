import { createRoot } from "react-dom/client";
import "@fontsource-variable/manrope";
import "@fontsource-variable/space-grotesk";
import "@fontsource-variable/newsreader/standard.css";
import "@fontsource-variable/newsreader/wght-italic.css";
import "./studio/studio.css";
import "./studio/pages.css";
import "./studio/quiet-room.css";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(<App />);
