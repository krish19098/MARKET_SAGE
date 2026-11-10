import { useState, type FormEvent } from "react";
import { post } from "../api";
import { ErrorNote } from "../components/ui";

export function Login({ onLogin }: { onLogin: (u: string) => void }) {
  const [username, setUsername] = useState("owner");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [error, setError] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const r = await post<{ user: string }>("/auth/login", { username, password, totp: totp || null });
      onLogin(r.user);
    } catch (err) {
      setError(err);
    }
  };
  return (
    <main className="login">
      <form onSubmit={submit} className="card">
        <h1>MARKET SAGE</h1>
        <p className="muted">Personal decision support · advisory and paper trading only</p>
        <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
        <label>Authenticator code (if enabled)<input inputMode="numeric" value={totp} onChange={(e) => setTotp(e.target.value)} autoComplete="one-time-code" /></label>
        <button type="submit">Sign in</button>
        {error != null && <ErrorNote error={error} />}
      </form>
    </main>
  );
}
