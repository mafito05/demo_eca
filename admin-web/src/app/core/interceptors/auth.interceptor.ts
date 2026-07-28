import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { BehaviorSubject, catchError, filter, switchMap, take, throwError } from 'rxjs';

import { AuthService } from '../services/auth.service';

/**
 * Estado compartido del refresco de token.
 *
 * Sin esto, si cinco peticiones fallan a la vez con 401, se disparan cinco refrescos en
 * paralelo: cuatro de ellos con un refresh token que el backend ya rotó, y el usuario acaba
 * expulsado a pesar de tener sesión válida. La primera petición refresca y las demás esperan.
 */
let refreshing = false;
const refreshed = new BehaviorSubject<string | null>(null);

/** Rutas que no deben llevar token ni intentar refrescar: son las que lo emiten. */
const PUBLIC_PATHS = ['/auth/login', '/auth/refresh', '/auth/demo-login'];

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const isPublic = PUBLIC_PATHS.some((path) => request.url.includes(path));
  // Las URLs prefirmadas de MinIO llevan su propia firma; añadirles `Authorization` hace que
  // S3 rechace la petición por conflicto de credenciales.
  const isPresigned = request.url.includes('X-Amz-Signature');

  const token = auth.accessToken;
  const authorized =
    token && !isPublic && !isPresigned
      ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
      : request;

  return next(authorized).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status !== 401 || isPublic || isPresigned || !auth.refreshToken) {
        return throwError(() => error);
      }

      if (refreshing) {
        return refreshed.pipe(
          filter((value): value is string => value !== null),
          take(1),
          switchMap((fresh) =>
            next(request.clone({ setHeaders: { Authorization: `Bearer ${fresh}` } })),
          ),
        );
      }

      refreshing = true;
      refreshed.next(null);

      return auth.refresh().pipe(
        switchMap((tokens) => {
          refreshing = false;
          refreshed.next(tokens.access_token);
          return next(
            request.clone({ setHeaders: { Authorization: `Bearer ${tokens.access_token}` } }),
          );
        }),
        catchError((refreshError) => {
          refreshing = false;
          auth.logout();
          return throwError(() => refreshError);
        }),
      );
    }),
  );
};
