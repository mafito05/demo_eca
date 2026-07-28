import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-login',
  imports: [FormsModule],
  template: `
    <div class="wrap">
      <form class="card" (ngSubmit)="submit()">
        <h1>DemoECA</h1>
        <p class="sub">Admin panel · MedTech Training</p>

        @if (error()) {
          <div class="alert error">{{ error() }}</div>
        }

        <div class="field">
          <label for="email">Email</label>
          <input id="email" name="email" type="email" [(ngModel)]="email" required autofocus />
        </div>

        <div class="field">
          <label for="password">Password</label>
          <input id="password" name="password" type="password" [(ngModel)]="password" required />
        </div>

        <button class="primary" type="submit" [disabled]="loading()">
          @if (loading()) {
            <span class="spinner"></span>
          } @else {
            Sign in
          }
        </button>

        <p class="hint">
          Demo credentials: <code>superadmin&#64;demoeca.example.com</code> /
          <code>Demo1234!</code>
        </p>
      </form>
    </div>
  `,
  styles: `
    .wrap {
      display: grid;
      place-items: center;
      min-height: 100vh;
      padding: 1rem;
    }
    form {
      width: 100%;
      max-width: 380px;
    }
    .sub {
      color: var(--text-dim);
      margin: 0 0 1.4rem;
      font-size: 0.88rem;
    }
    button {
      width: 100%;
    }
  `,
})
export class LoginComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  email = 'superadmin@demoeca.example.com';
  password = 'Demo1234!';
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  submit(): void {
    this.loading.set(true);
    this.error.set(null);

    this.auth.login(this.email, this.password).subscribe({
      next: () => {
        // Se carga el usuario antes de navegar: el shell necesita el rol para pintar el menú,
        // y el guard lo necesita para decidir. Navegar antes provoca un parpadeo del menú.
        this.auth.loadCurrentUser().subscribe({
          next: (user) => {
            this.loading.set(false);
            if (user.role === 'trainee') {
              this.auth.logout();
              this.error.set(
                'This panel is for administrators only. Training users go through the mobile app.',
              );
              return;
            }
            void this.router.navigate(['/agent/playground']);
          },
          error: () => {
            this.loading.set(false);
            this.error.set('Could not load the user profile.');
          },
        });
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(
          err?.status === 401
            ? 'Incorrect email or password.'
            : `Could not reach the server (${err?.status ?? 'no response'}). Is the backend running?`,
        );
      },
    });
  }
}
