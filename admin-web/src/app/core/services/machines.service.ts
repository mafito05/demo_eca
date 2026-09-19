import { HttpClient, HttpEvent, HttpEventType } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, concat, map, of, switchMap } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  Machine,
  MachineImage,
  MachineImageRole,
  MachineImageUploadTicket,
  QrExport,
  Specialty,
  PublishStatus,
} from '../models/api.models';

/** Estado de una subida de imagen. Mismo contrato que el de video (ver `UploadState`). */
export interface ImageUploadState {
  progress: number;
  imageId?: string;
  /** Solo `true` cuando el PUT ha respondido: es la señal para llamar a `confirmImage`. */
  done?: boolean;
}

@Injectable({ providedIn: 'root' })
export class MachinesService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/machines`;

  list(): Observable<Machine[]> {
    return this.http.get<Machine[]>(this.base);
  }

  create(payload: {
    code: string;
    name: string;
    manufacturer?: string | null;
    specialty: Specialty;
    description?: string | null;
    status: PublishStatus;
  }): Observable<Machine> {
    return this.http.post<Machine>(this.base, payload);
  }

  update(
    machineId: string,
    payload: Partial<{
      code: string;
      name: string;
      manufacturer: string | null;
      specialty: Specialty;
      description: string | null;
      status: PublishStatus;
    }>,
  ): Observable<Machine> {
    return this.http.patch<Machine>(`${this.base}/${machineId}`, payload);
  }

  qrData(machineId: string): Observable<QrExport> {
    return this.http.get<QrExport>(`${this.base}/${machineId}/qr-data`);
  }

  /**
   * Descarga el QR como blob.
   *
   * No se puede usar un `<img src="...">` directo: el endpoint exige la cabecera
   * `Authorization`, y una etiqueta `img` no la envía. Se pide con HttpClient (el interceptor
   * añade el token) y se convierte a object URL.
   */
  qrImage(machineId: string, format: 'png' | 'svg'): Observable<Blob> {
    return this.http.get(`${this.base}/${machineId}/qr.${format}`, { responseType: 'blob' });
  }

  // ---------------------------------------------------------------------------
  //  Imágenes de producto (D-058)
  // ---------------------------------------------------------------------------
  //
  // A diferencia del QR, estas imágenes SÍ se pueden pintar con un `<img src>` normal: viven en
  // un bucket con lectura anónima y su URL no lleva firma ni caduca. Por eso aquí no hay nada
  // parecido al truco del blob de `qrImage`.

  images(machineId: string): Observable<MachineImage[]> {
    return this.http.get<MachineImage[]>(`${this.base}/${machineId}/images`);
  }

  patchImage(
    machineId: string,
    imageId: string,
    payload: Partial<{ alt_text: string | null; order_index: number; role: MachineImageRole }>,
  ): Observable<MachineImage> {
    return this.http.patch<MachineImage>(`${this.base}/${machineId}/images/${imageId}`, payload);
  }

  deleteImage(machineId: string, imageId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${machineId}/images/${imageId}`);
  }

  confirmImage(machineId: string, imageId: string): Observable<MachineImage> {
    return this.http.post<MachineImage>(
      `${this.base}/${machineId}/images/${imageId}/confirm`,
      {},
    );
  }

  /**
   * Sube una imagen en dos fases, igual que el video (D-010).
   *
   * El `Content-Type` del PUT es el que MinIO almacena, y `confirm` valida **ese** valor contra
   * la allowlist. Se manda el que devuelve el ticket y no `file.type`: si el navegador no
   * reconoce la extensión, `file.type` viene vacío y el objeto quedaría guardado como
   * `application/octet-stream`, que `confirm` rechazaría después de haber subido los bytes.
   */
  uploadImage(
    machineId: string,
    file: File,
    role: MachineImageRole = 'gallery',
  ): Observable<ImageUploadState> {
    return this.http
      .post<MachineImageUploadTicket>(`${this.base}/${machineId}/images/upload-url`, {
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
        role,
      })
      .pipe(
        switchMap((ticket) =>
          concat(
            of<ImageUploadState>({ progress: 0, imageId: ticket.image_id }),
            this.http
              .put(ticket.upload_url, file, {
                headers: { 'Content-Type': ticket.required_content_type },
                reportProgress: true,
                observe: 'events',
              })
              .pipe(
                map((event: HttpEvent<unknown>): ImageUploadState => {
                  if (event.type === HttpEventType.UploadProgress && event.total) {
                    return { progress: Math.round((event.loaded / event.total) * 100) };
                  }
                  if (event.type === HttpEventType.Response) {
                    return { progress: 100, imageId: ticket.image_id, done: true };
                  }
                  return { progress: -1 };
                }),
              ),
          ),
        ),
      );
  }
}
