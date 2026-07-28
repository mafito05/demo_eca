import { Routes } from '@angular/router';

import { authGuard, roleGuard } from './core/guards/auth.guard';

/**
 * Rutas del panel.
 *
 * Todo con `loadComponent` (lazy): el panel crecerá con el editor de contenido y el constructor
 * de evaluaciones, y cargarlo entero en el primer arranque no escala.
 *
 * **El Agent Builder está consolidado bajo una ruta padre con cinco hijas** (D-042). Antes eran
 * cinco entradas independientes del menú lateral, que las presentaba como cinco módulos sin
 * relación cuando son cinco caras de la misma herramienta. Con rutas hijas se conserva lo que
 * importa: cada pestaña sigue siendo una URL real, compartible y capturable, y sigue cargándose
 * de forma diferida solo cuando se visita.
 *
 * No se usa `loadChildren` sobre un `agent.routes.ts` porque eso metería `tools` y `credentials`
 * en el mismo chunk que ve un `admin`, que nunca puede abrirlas.
 *
 * `data.breadcrumb` alimenta la barra superior recorriendo el árbol activo. Cualquier ruta nueva
 * aparece ahí sola; una lista paralela se desincronizaría.
 */
export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login.component').then((m) => m.LoginComponent),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./layout/shell.component').then((m) => m.ShellComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'dashboard',
        data: { breadcrumb: 'Overview' },
        loadComponent: () =>
          import('./features/dashboard/dashboard.component').then((m) => m.DashboardComponent),
      },
      {
        path: 'machines',
        data: { breadcrumb: 'Equipment & QR' },
        loadComponent: () =>
          import('./features/machines/machines.component').then((m) => m.MachinesComponent),
      },
      {
        path: 'lms',
        data: { breadcrumb: 'Training' },
        loadComponent: () => import('./features/lms/lms.component').then((m) => m.LmsComponent),
      },
      {
        path: 'agent',
        data: { breadcrumb: 'Agent Builder' },
        loadComponent: () =>
          import('./features/agent-builder/agent-layout.component').then(
            (m) => m.AgentLayoutComponent,
          ),
        children: [
          { path: '', pathMatch: 'full', redirectTo: 'playground' },
          {
            path: 'playground',
            data: { breadcrumb: 'Playground' },
            loadComponent: () =>
              import('./features/agent-builder/playground.component').then(
                (m) => m.PlaygroundComponent,
              ),
          },
          {
            path: 'agents',
            data: { breadcrumb: 'Agents' },
            loadComponent: () =>
              import('./features/agent-builder/agent-config.component').then(
                (m) => m.AgentConfigComponent,
              ),
          },
          {
            path: 'knowledge',
            data: { breadcrumb: 'Knowledge' },
            loadComponent: () =>
              import('./features/agent-builder/knowledge.component').then(
                (m) => m.KnowledgeComponent,
              ),
          },
          {
            path: 'providers',
            data: { breadcrumb: 'Providers' },
            canActivate: [roleGuard('superadmin')],
            loadComponent: () =>
              import('./features/agent-builder/credentials.component').then(
                (m) => m.CredentialsComponent,
              ),
          },
          {
            path: 'tools',
            data: { breadcrumb: 'Tools' },
            canActivate: [roleGuard('superadmin')],
            loadComponent: () =>
              import('./features/agent-builder/tools.component').then((m) => m.ToolsComponent),
          },
        ],
      },

      // Compatibilidad con las URLs anteriores: hay capturas, documentación y marcadores que
      // apuntan a ellas. Cuestan dos líneas y evitan un 404 sin explicación.
      { path: 'agent/config', redirectTo: 'agent/agents' },
      { path: 'agent/credentials', redirectTo: 'agent/providers' },
    ],
  },
  { path: '**', redirectTo: '' },
];
