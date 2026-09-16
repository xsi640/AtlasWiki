import { createBrowserRouter } from "react-router-dom";
import { App } from "./App";

/** 13 页路由表，路径与 UX 设计稿一致。 */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, lazy: () => import("./pages/HomePage").then((m) => ({ Component: m.HomePage })) },
      { path: "ingest", lazy: () => import("./pages/IngestPage").then((m) => ({ Component: m.IngestPage })) },
      { path: "compile", lazy: () => import("./pages/CompilePage").then((m) => ({ Component: m.CompilePage })) },
      { path: "changes", lazy: () => import("./pages/ChangesPage").then((m) => ({ Component: m.ChangesPage })) },
      { path: "page/:name", lazy: () => import("./pages/PageDetailPage").then((m) => ({ Component: m.PageDetailPage })) },
      { path: "graph", lazy: () => import("./pages/GraphPage").then((m) => ({ Component: m.GraphPage })) },
      { path: "zones", lazy: () => import("./pages/ZonesPage").then((m) => ({ Component: m.ZonesPage })) },
      { path: "zones/:name", lazy: () => import("./pages/ZoneDetailPage").then((m) => ({ Component: m.ZoneDetailPage })) },
      { path: "search", lazy: () => import("./pages/SearchPage").then((m) => ({ Component: m.SearchPage })) },
      { path: "history", lazy: () => import("./pages/HistoryPage").then((m) => ({ Component: m.HistoryPage })) },
      { path: "sources", lazy: () => import("./pages/SourcesPage").then((m) => ({ Component: m.SourcesPage })) },
      { path: "sources/:id", lazy: () => import("./pages/SourceDetailPage").then((m) => ({ Component: m.SourceDetailPage })) },
      { path: "lint", lazy: () => import("./pages/LintPage").then((m) => ({ Component: m.LintPage })) },
      { path: "settings", lazy: () => import("./pages/SettingsPage").then((m) => ({ Component: m.SettingsPage })) },
    ],
  },
]);
