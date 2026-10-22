import { useEffect } from "react";
import { useState, FormEvent } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { useAuth } from "../services/auth";

export default function Login() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (auth.token) return <Navigate to="/dashboard" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.login(username, password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "No se pudo autenticar: verifica los datos."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-full flex items-center justify-center p-4 bg-slate-900">
      <form
        onSubmit={onSubmit}
        className="bg-white rounded-2xl p-8 w-full max-w-sm shadow-2xl"
      >
        <h1 className="text-xl font-bold">Panel administrativo</h1>
        <p className="text-slate-600 text-sm mt-1">proyectoC3 · Raspberry Pi</p>
        <label className="block mt-6 text-sm font-medium">Usuario</label>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          autoComplete="username"
          className="mt-1 border rounded-lg px-3 py-2 w-full"
        />
        <label className="block mt-3 text-sm font-medium">Contraseña</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="current-password"
          className="mt-1 border rounded-lg px-3 py-2 w-full"
        />
        {error && (
          <div className="mt-4 text-sm bg-red-50 text-red-700 rounded-lg p-3">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={busy}
          className="mt-6 bg-brand-500 text-white rounded-lg px-4 py-2 w-full disabled:opacity-50"
        >
          {busy ? "Validando..." : "Entrar"}
        </button>
        <p className="mt-4 text-xs text-slate-500">
          La cuenta inicial se crea en la Raspberry Pi con{" "}
          <code>python -m device.cli init-admin</code>.
        </p>
      </form>
    </div>
  );
}
