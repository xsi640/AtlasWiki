import { useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/", label: "首页", end: true },
  { to: "/ingest", label: "投放" },
  { to: "/graph", label: "图谱" },
  { to: "/search", label: "搜索" },
  { to: "/lint", label: "体检" },
  { to: "/settings", label: "设置" },
];

export function App() {
  const location = useLocation();

  useEffect(() => {
    document.documentElement.dataset.theme =
      window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-title">LLM Wiki</span>
        <nav className="app-nav" aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="app-main" key={location.pathname}>
        <Outlet />
      </main>
    </div>
  );
}
