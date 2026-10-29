import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { Studio } from "./pages/Studio";
import { Models } from "./pages/Models";
import { SettingsPage } from "./pages/Settings";
import { Link } from "react-router-dom";
import { Card, EmptyState, Button } from "./components/ui";
import { Film } from "lucide-react";

function NotFound() {
  return (
    <Card>
      <EmptyState
        icon={<Film size={30} />}
        title="Página no encontrada"
        description="El enlace no existe o el proyecto fue eliminado."
        action={
          <Link to="/">
            <Button variant="primary">Volver al panel</Button>
          </Link>
        }
      />
    </Card>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/projects/:projectId" element={<Studio />} />
        <Route path="/models" element={<Models />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
