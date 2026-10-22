import { Routes, Route, Navigate } from "react-router-dom";
import { ProtectedLayout } from "./components/Layout";
import Login from "./routes/Login";
import Dashboard from "./routes/Dashboard";
import People from "./routes/People";
import PersonNew from "./routes/PersonNew";
import PersonDetail from "./routes/PersonDetail";
import AccessHistory from "./routes/AccessHistory";
import Camera from "./routes/Camera";
import Roles from "./routes/Roles";
import Settings from "./routes/Settings";
import Welcome from "./routes/Welcome";
import Denied from "./routes/Denied";

export default function App() {
  return (
    <Routes>
      {/* públicas: muestran la decisión del dispositivo */ }
      <Route path="/welcome" element={<Welcome />} />
      <Route path="/denied" element={<Denied />} />
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      {/* administrativas: cada operación se valida en el backend */}
      <Route element={<ProtectedLayout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/people" element={<People />} />
        <Route path="/people/new" element={<PersonNew />} />
        <Route path="/people/:id" element={<PersonDetail />} />
        <Route path="/access-history" element={<AccessHistory />} />
        <Route path="/camera" element={<Camera />} />
        <Route path="/roles" element={<Roles />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
