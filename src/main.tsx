import { createRoot } from "react-dom/client";
import "@fontsource-variable/dm-sans";
import "@fontsource-variable/manrope";
import { App } from "./App";
import "./music-studio/studio.css";
createRoot(document.getElementById("root")!).render(<App />);
