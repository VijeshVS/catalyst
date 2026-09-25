import { Outlet } from 'react-router-dom';

import { GlobalHeader } from './GlobalHeader';
import { Sidebar } from './Sidebar';

export function AppShell() {
  return (
    <div className="app-shell">
      <GlobalHeader />
      <div className="app-body">
        <Sidebar />
        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
