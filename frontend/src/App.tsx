import { Route, Routes } from 'react-router-dom';

import './App.css';
import { ProtectedRoute, PublicOnlyRoute } from './auth/AuthContext';
import { AppShell } from './components/AppShell';
import { ApiKeysPage } from './pages/ApiKeysPage';
import { AppEntryPage } from './pages/AppEntryPage';
import { CreateProjectPage } from './pages/CreateProjectPage';
import { EnvironmentsPage } from './pages/EnvironmentsPage';
import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { OrgDashboard } from './pages/OrgDashboard';
import { OrgOnboardingPage } from './pages/OrgOnboardingPage';
import { ProjectDetail } from './pages/ProjectDetail';
import { ProjectLayout } from './pages/ProjectLayout';
import { RegisterPage } from './pages/RegisterPage';
import { AuditPage } from './pages/AuditPage';
import { SettingsPage } from './pages/SettingsPage';
import { WorkspaceProvider } from './workspace/WorkspaceContext';

function NotFoundPage() {
  return (
    <div className="public-not-found">
      <span className="brand-logo">C</span>
      <span className="eyebrow">404 · Off the map</span>
      <h1>That route doesn’t exist.</h1>
      <a className="btn-primary" href="/">Return home <span aria-hidden="true">→</span></a>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<PublicOnlyRoute><LoginPage /></PublicOnlyRoute>} />
      <Route path="/register" element={<PublicOnlyRoute><RegisterPage /></PublicOnlyRoute>} />
      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <WorkspaceProvider>
              <AppShell />
            </WorkspaceProvider>
          </ProtectedRoute>
        }
      >
        <Route index element={<AppEntryPage />} />
        <Route path="orgs/new" element={<OrgOnboardingPage />} />
        <Route path="orgs/:orgId" element={<OrgDashboard />} />
        <Route path="orgs/:orgId/projects/new" element={<CreateProjectPage />} />
        <Route path="orgs/:orgId/projects/:projectId" element={<ProjectLayout />}>
          <Route index element={<ProjectDetail />} />
          <Route path="environments" element={<EnvironmentsPage />} />
          <Route path="keys" element={<ApiKeysPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default App;
