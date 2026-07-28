import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

/**
 * Raíz de la aplicación: solo la salida del router.
 *
 * El armazón con menú lateral vive en `ShellComponent`, colgado de la ruta autenticada, para que
 * la pantalla de login no lo herede.
 */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  template: '<router-outlet />',
})
export class App {}
