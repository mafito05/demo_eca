import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';

import { environment } from '../../../environments/environment';
import { TokenPair, User, UserRole } from '../models/api.models';

const ACCESS_KEY = 'demoeca.access';
const REFRESH_KEY = 'demoeca.refresh';

/**
 * Autenticación del panel.
 *
 * Los tokens se guardan en `localStorage`. Es lo habitual en una SPA y suficiente para una
 * herramienta de backoffice, pero conviene saber el compromiso: un XSS puede leerlos. La
 * alternativa robusta son cookies `HttpOnly` + `SameSite`, que exige que el backend emita
 * cookies y gestione CSRF. Está anotado como deuda consciente, no como descuido.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  /** Signal en lugar de BehaviorSubject: es el modelo reactivo actual de Angular. */
  readonly currentUser = signal<User | null>(null);
  readonly isAuthenticated = computed(() => this.currentUser() !== null);
  /** El panel oculta lo que el backend prohibiría; la UI no es el control de acceso. */
  readonly isSuperadmin = computed(() => this.currentUser()?.role === 'superadmin');

  get accessToken(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  }

  get refreshToken(): string | null {
    return localStorage.getItem(REFRESH_KEY);
  }

  login(email: string, password: string): Observable<TokenPair> {
    return this.http
      .post<TokenPair>(`${environment.apiUrl}/auth/login`, { email, password })
      .pipe(tap((tokens) => this.storeTokens(tokens)));
  }

  /** Recupera el usuario a partir del token guardado, al recargar la página. */
  loadCurrentUser(): Observable<User> {
    return this.http
      .get<User>(`${environment.apiUrl}/auth/me`)
      .pipe(tap((user) => this.currentUser.set(user)));
  }

  refresh(): Observable<TokenPair> {
    return this.http
      .post<TokenPair>(`${environment.apiUrl}/auth/refresh`, { refresh_token: this.refreshToken })
      .pipe(tap((tokens) => this.storeTokens(tokens)));
  }

  logout(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    this.currentUser.set(null);
    void this.router.navigate(['/login']);
  }

  hasRole(...roles: UserRole[]): boolean {
    const role = this.currentUser()?.role;
    return role !== undefined && roles.includes(role);
  }

  private storeTokens(tokens: TokenPair): void {
    localStorage.setItem(ACCESS_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  }
}
