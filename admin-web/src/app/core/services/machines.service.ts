import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Machine, QrExport, Specialty, PublishStatus } from '../models/api.models';

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
}
