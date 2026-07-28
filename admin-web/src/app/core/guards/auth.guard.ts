import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { AuthService } from '../services/auth.service';
import { UserRole } from '../models/api.models';

/**
 * Exige sesión. Si hay token pero no hay usuario en memoria (recarga de página), lo recupera
 * del backend antes de decidir.
 */
export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.isAuthenticated()) {
    return true;
  }

  if (!auth.accessToken) {
    return router.createUrlTree(['/login'], { queryParams: { redirect: state.url } });
  }

  return auth.loadCurrentUser().pipe(
    map((user) => {
      // El panel es solo backoffice: un trainee con token válido no entra aquí.
      if (user.role === 'trainee') {
        auth.logout();
        return router.createUrlTree(['/login'], { queryParams: { reason: 'backoffice-only' } });
      }
      return true;
    }),
    catchError(() => of(router.createUrlTree(['/login']))),
  );
};

/**
 * Exige un rol concreto. Replica lo que el backend ya aplica: la UI oculta, el backend prohíbe.
 * Ocultar sin comprobar en el servidor no es seguridad, es maquillaje.
 */
export const roleGuard = (...roles: UserRole[]): CanActivateFn => {
  return () => {
    const auth = inject(AuthService);
    const router = inject(Router);
    return auth.hasRole(...roles) ? true : router.createUrlTree(['/machines']);
  };
};
