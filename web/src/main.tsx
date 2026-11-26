import React from "react";
import { createRoot } from "react-dom/client";

import "@fontsource/atkinson-hyperlegible/400.css";
import "@fontsource/atkinson-hyperlegible/400-italic.css";
import "@fontsource/atkinson-hyperlegible/700.css";

import App from "./App";
import "./style.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("no #root element to mount into");
}
createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
