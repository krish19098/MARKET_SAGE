import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api, ApiError } from "./api";
import { Home } from "./screens/Home";
import { Invest } from "./screens/Invest";
import { Trades } from "./screens/Trades";
import { Analyst } from "./screens/Analyst";
import { Performance } from "./screens/Performance";
import { Alerts } from "./screens/Alerts";
import { Login } from "./screens/Login";

export const NAV = [
  { to: "/", label: "Home", icon: "⌂" },
  { to: "/invest", label: "Invest", icon: "₹" },
  { to: "/trades", label: "My Trades", icon: "≡" },
  { to: "/analyst", label: "Analyst", icon: "⌕" },
  { to: "/performance", label: "Performance", icon: "◎" },
];

export function App() {
  const [user, setUser] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    api<{ user: string }>("/auth/me")
      .then((r) => setUser(r.user))
      .catch((e) => setUser(e instanceof ApiError && e.status === 401 ? null : null));
  }, []);
  if (user === undefined) return <p className="muted center">Loading…</p>;
  if (user === null) return <Login onLogin={setUser} />;
  return (
    <div className="shell">
      <nav className="nav" aria-label="Primary">
        <div className="brand">MARKET SAGE</div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === "/"} className="nav-link">
            <span className="nav-icon" aria-hidden>{n.icon}</span>
            <span className="nav-label">{n.label}</span>
          </NavLink>
        ))}
        <p className="nav-foot muted">Advisory · paper trading only</p>
      </nav>
      <main className="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/invest" element={<Invest />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/analyst" element={<Analyst />} />
          <Route path="/analyst/:exchange/:symbol" element={<Analyst />} />
          <Route path="/performance" element={<Performance />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
