import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';

import { IconComponent } from '../icon/icon.component';

/**
 * Zona de subida: arrastrar y soltar, o pulsar para elegir.
 *
 * **No hace HTTP a propósito.** El flujo de dos fases (pedir ticket -> PUT prefirmado ->
 * confirmar) vive en el servicio y en el componente padre. Así este componente vale igual para
 * un video de 2 GB y para una foto de 200 KB sin un solo condicional dentro, y el detalle
 * delicado —cuándo se encola el procesado— se queda en un único sitio.
 *
 * Sustituye al `<input type="file">` pelado que había en la pantalla de capacitación, que era el
 * único punto de subida del panel y no se podía reutilizar en máquinas.
 */
@Component({
  selector: 'app-file-drop',
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!--
      Un <label> envolviendo el <input>, y no un <div tabindex="0">: el foco de teclado, Enter,
      Espacio y el clic funcionan de forma nativa y se anuncian bien. Con un div habría que
      reimplementar los tres y aun así quedaría peor para un lector de pantalla.
    -->
    <label
      class="dropzone"
      [class.over]="dragOver()"
      [class.busy]="busy()"
      [class.disabled]="disabled()"
      (dragenter)="onDragEnter($event)"
      (dragover)="onDragOver($event)"
      (dragleave)="onDragLeave($event)"
      (drop)="onDrop($event)"
    >
      <input
        type="file"
        class="sr-only"
        [accept]="accept()"
        [multiple]="multiple()"
        [disabled]="disabled() || busy()"
        (change)="onPick($event)"
      />

      @if (busy()) {
        <span class="trunc name">{{ fileName() || 'Uploading…' }}</span>
        <div class="meter">
          <div
            class="meter-fill"
            [class.indeterminate]="!hasProgress()"
            [style.width.%]="hasProgress() ? progress() : 100"
          ></div>
        </div>
        <span class="hint">{{ hasProgress() ? progress() + '%' : 'Starting…' }}</span>
        <button type="button" class="small danger-outline" (click)="onCancel($event)">
          Cancel
        </button>
      } @else {
        <app-icon name="upload" [size]="26" />
        <strong>{{ label() }}</strong>
        <span class="hint">{{ hintLine() }}</span>
      }
    </label>

    @if (localError(); as message) {
      <div class="alert error">{{ message }}</div>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    .dropzone {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: var(--sp-2);
      min-height: 120px;
      padding: var(--sp-4);
      text-align: center;
      cursor: pointer;
      border: 1px dashed var(--border-strong);
      border-radius: var(--radius);
      background: var(--surface-2);
      color: var(--text-dim);
      transition:
        border-color var(--dur-fast) var(--ease),
        background var(--dur-fast) var(--ease);
    }
    .dropzone:hover:not(.disabled):not(.busy),
    .dropzone:focus-within {
      border-color: var(--accent);
      background: var(--accent-soft);
    }
    .dropzone.over {
      border-color: var(--accent);
      background: var(--accent-soft);
      border-style: solid;
    }
    .dropzone.busy {
      cursor: default;
    }
    .dropzone.disabled {
      cursor: not-allowed;
      opacity: 0.55;
    }
    .dropzone strong {
      color: var(--text);
      font-size: var(--fs-base);
    }
    .name {
      max-width: 100%;
      color: var(--text);
      font-size: var(--fs-sm);
      font-weight: var(--fw-med);
    }
    .meter {
      width: 100%;
    }
    /* Barrido para cuando no hay porcentaje fiable: es lo que hace que el centinela -1 del
       servicio sea inofensivo aunque llegue, sin que este componente sepa que existe. */
    .meter-fill.indeterminate {
      animation: sweep 1.1s ease-in-out infinite;
      transform-origin: left;
    }
    @keyframes sweep {
      0% {
        transform: scaleX(0.15) translateX(0);
      }
      50% {
        transform: scaleX(0.5) translateX(100%);
      }
      100% {
        transform: scaleX(0.15) translateX(560%);
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .meter-fill.indeterminate {
        animation: none;
      }
    }
    .alert {
      margin-top: var(--sp-2);
    }
  `,
})
export class FileDropComponent {
  /** Igual que el atributo `accept` nativo: `video/*`, `image/jpeg,image/png`… */
  readonly accept = input('*/*');
  /** 0 = sin límite. Se compara contra `file.size` antes de emitir nada. */
  readonly maxSizeMb = input(0);
  readonly label = input('Drop a file here, or click to browse');
  readonly hint = input<string | null>(null);
  readonly disabled = input(false);
  readonly busy = input(false);
  /** 0..100, o null / negativo para medidor indeterminado. */
  readonly progress = input<number | null>(null);
  readonly fileName = input<string | null>(null);
  readonly multiple = input(false);

  readonly picked = output<File[]>();
  readonly cancel = output<void>();
  readonly rejected = output<{ file: File; reason: 'type' | 'size' }>();

  protected readonly dragOver = signal(false);
  protected readonly localError = signal<string | null>(null);

  // `dragenter`/`dragleave` se disparan también al pasar sobre los hijos del recuadro. Sin este
  // contador, el resaltado parpadea mientras el puntero cruza el icono o el texto.
  private dragDepth = 0;

  protected readonly hasProgress = computed(() => {
    const value = this.progress();
    return value !== null && value >= 0;
  });

  protected readonly hintLine = computed(() => {
    const custom = this.hint();
    if (custom) return custom;
    const limit = this.maxSizeMb();
    const kinds = this.accept() === '*/*' ? 'Any file' : this.accept();
    return limit > 0 ? `${kinds} · max ${limit} MB` : kinds;
  });

  protected onPick(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    // Se limpia ANTES de validar. Sin esto, volver a elegir el mismo fichero no dispara `change`
    // y la pantalla parece colgada — era la causa del "no se pueden subir videos".
    input.value = '';
    this.emit(files);
  }

  protected onDragEnter(event: DragEvent): void {
    if (this.disabled() || this.busy()) return;
    event.preventDefault();
    this.dragDepth += 1;
    this.dragOver.set(true);
  }

  protected onDragOver(event: DragEvent): void {
    if (this.disabled() || this.busy()) return;
    // Sin `preventDefault` el navegador abre el fichero en la pestaña en lugar de soltarlo aquí.
    event.preventDefault();
  }

  protected onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.dragDepth = Math.max(0, this.dragDepth - 1);
    if (this.dragDepth === 0) this.dragOver.set(false);
  }

  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragDepth = 0;
    this.dragOver.set(false);
    if (this.disabled() || this.busy()) return;
    this.emit(Array.from(event.dataTransfer?.files ?? []));
  }

  protected onCancel(event: Event): void {
    // El <label> propagaría el clic al <input> y volvería a abrir el diálogo de ficheros.
    event.preventDefault();
    event.stopPropagation();
    this.cancel.emit();
  }

  private emit(files: File[]): void {
    this.localError.set(null);
    if (!files.length) return;

    const accepted: File[] = [];
    for (const file of files) {
      if (!this.typeAllowed(file)) {
        this.fail(file, 'type', `“${file.name}” is not an accepted file type.`);
        continue;
      }
      const limit = this.maxSizeMb();
      if (limit > 0 && file.size > limit * 1024 * 1024) {
        const mb = (file.size / 1024 / 1024).toFixed(1);
        this.fail(file, 'size', `“${file.name}” is ${mb} MB, over the ${limit} MB limit.`);
        continue;
      }
      accepted.push(file);
    }

    if (accepted.length) {
      this.picked.emit(this.multiple() ? accepted : [accepted[0]]);
    }
  }

  private fail(file: File, reason: 'type' | 'size', message: string): void {
    this.localError.set(message);
    this.rejected.emit({ file, reason });
  }

  /** Compara contra `accept`, soportando tanto `image/png` como el comodín `video/*`. */
  private typeAllowed(file: File): boolean {
    const accept = this.accept().trim();
    if (!accept || accept === '*/*') return true;

    return accept.split(',').some((raw) => {
      const rule = raw.trim().toLowerCase();
      if (!rule) return false;
      if (rule.startsWith('.')) return file.name.toLowerCase().endsWith(rule);
      if (rule.endsWith('/*')) return file.type.toLowerCase().startsWith(rule.slice(0, -1));
      return file.type.toLowerCase() === rule;
    });
  }
}
