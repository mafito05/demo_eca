import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';

import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    // OBLIGATORIO, y su ausencia fue un bug real (D-054): el proyecto no carga zone.js, y sin
    // este provider tampoco hay planificador zoneless — un `signal.set()` desde un callback de
    // HTTP marcaba la vista como sucia pero NADIE programaba el repintado. El síntoma: la subida
    // de video completaba todas sus peticiones (PUT presignado incluido) y la pantalla se
    // quedaba como si nada hubiera pasado. Solo se repintaba lo que coincidía con una
    // navegación del router.
    provideZonelessChangeDetection(),
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    // El interceptor añade el Bearer y gestiona el refresco de token. Se registra una sola vez
    // aquí: cada servicio usa HttpClient a secas y no sabe nada de autenticación.
    provideHttpClient(withInterceptors([authInterceptor])),
  ],
};
