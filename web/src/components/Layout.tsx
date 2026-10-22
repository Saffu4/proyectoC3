import { Navigate, Outlet, useLocation } from "react-router-dom";
import { GitBranch, LogOut } from "lucide-react";
import { useAuth } from "../services/auth";

export function ProtectedLayout() {
  const auth = useAuth();

  if (!auth.token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return (
    <div className="flex h-full">
      <aside className="w-56 shrink-0 border-r bg-slate-900 text-slate-200 p-4 flex flex-col gap-2 max-md:hidden">
        <div className="font-bold text-lg mb-2 flex items-center gap-2">
          <GitBranch className="text-brand-500" /> proyectoC3
        </div>
        {[
          ["/dashboard", "Dashboard"],
          ["/people", "Personas"],
          ["/access-history", "Historial"],
          ["/camera", "Cámara en vivo"],
          ["/roles", "Roles y permisos"],
          ["/settings", "Configuración"],
        ].map(([to, label]) => (
          <a
            key={to}
            href={to}
            className="px-3 py-2 rounded hover:bg-slate-800 text-sm"
          >
            {label}
          </a>
        ))}
        <button
          onClick={() => auth.logout()}
          className="mt-auto px-3 py-2 rounded text-sm hover:bg-slate-800 flex items-center gap-2"
        >
          <LogOut size={16} /> Salir
        </button>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
