import { HttpClient, HttpEvent, HttpEventType, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, concat, map, of, switchMap } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  AuthoringTree,
  Lesson,
  LearningPath,
  TrainingModule,
  VideoAsset,
  VideoAssetListItem,
  VideoUploadTicket,
} from '../models/api.models';

/** Estado de una subida en curso, común a videos e imágenes. */
export interface UploadState {
  /** 0..100. **-1 significa "evento sin progreso útil"** y el consumidor debe ignorarlo. */
  progress: number;
  /** Disponible desde que responde el ticket, no al terminar: permite cancelar y limpiar. */
  videoAssetId?: string;
  /**
   * Solo `true` cuando el PUT ha respondido. **Es esta la señal para encolar el procesado**, no
   * la presencia de `videoAssetId`: ese llega al principio, y encolar entonces procesaría un
   * objeto que todavía no está en MinIO.
   */
  done?: boolean;
}

@Injectable({ providedIn: 'root' })
export class LmsService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/lms`;

  listModules(machineModelId: string): Observable<TrainingModule[]> {
    return this.http.get<TrainingModule[]>(`${this.base}/modules`, {
      params: { machine_model_id: machineModelId },
    });
  }

  createModule(payload: Partial<TrainingModule> & { machine_model_id: string; title: string }) {
    return this.http.post<TrainingModule>(`${this.base}/modules`, payload);
  }

  createLesson(
    payload: Partial<Lesson> & {
      training_module_id: string;
      title: string;
      body?: string | null;
      document_key?: string | null;
    },
  ) {
    return this.http.post<Lesson>(`${this.base}/lessons`, payload);
  }

  updateModule(moduleId: string, payload: Partial<TrainingModule>) {
    return this.http.patch<TrainingModule>(`${this.base}/modules/${moduleId}`, payload);
  }

  deleteModule(moduleId: string) {
    return this.http.delete<void>(`${this.base}/modules/${moduleId}`);
  }

  updateLesson(lessonId: string, payload: Partial<Lesson> & { body?: string | null }) {
    return this.http.patch<Lesson>(`${this.base}/lessons/${lessonId}`, payload);
  }

  deleteLesson(lessonId: string) {
    return this.http.delete<void>(`${this.base}/lessons/${lessonId}`);
  }

  /**
   * Árbol de autoría: todos los módulos y lecciones CON sus campos editables (D-052).
   *
   * El `learningPath` de consumo omite `body`, `video_asset_id` y los estados de publicación,
   * así que un formulario de edición precargado necesita este endpoint.
   */
  authoring(machineModelId: string): Observable<AuthoringTree> {
    return this.http.get<AuthoringTree>(`${this.base}/machines/${machineModelId}/authoring`);
  }

  /** Vista del trainee: sirve al panel para previsualizar lo que verá el médico. */
  learningPath(machineModelId: string): Observable<LearningPath> {
    return this.http.get<LearningPath>(`${this.base}/machines/${machineModelId}/path`);
  }

  /**
   * Biblioteca de videos: todos los assets con su estado y las lecciones que los usan.
   *
   * Sin parámetros devuelve todo; con `machineModelId` filtra por equipo y con `unassigned` los
   * que aún no tienen ninguno (los dos a la vez son un 422 del backend).
   */
  listVideos(
    scope?: { machineModelId?: string; unassigned?: boolean },
  ): Observable<VideoAssetListItem[]> {
    let params = new HttpParams();
    if (scope?.machineModelId) {
      params = params.set('machine_model_id', scope.machineModelId);
    } else if (scope?.unassigned) {
      params = params.set('unassigned', 'true');
    }
    return this.http.get<VideoAssetListItem[]>(`${this.base}/videos`, { params });
  }

  /** Reasigna (o desasigna, con null) el equipo de un video ya subido. */
  assignVideo(videoAssetId: string, machineModelId: string | null): Observable<VideoAsset> {
    return this.http.patch<VideoAsset>(`${this.base}/videos/${videoAssetId}`, {
      machine_model_id: machineModelId,
    });
  }

  deleteVideo(videoAssetId: string) {
    return this.http.delete<void>(`${this.base}/videos/${videoAssetId}`);
  }

  videoAsset(videoAssetId: string): Observable<VideoAsset> {
    return this.http.get<VideoAsset>(`${this.base}/videos/${videoAssetId}`);
  }

  processVideo(videoAssetId: string): Observable<VideoAsset> {
    return this.http.post<VideoAsset>(`${this.base}/videos/${videoAssetId}/process`, {});
  }

  /**
   * Sube un video en dos fases (D-010): se pide un ticket y el fichero va **directo a MinIO**.
   *
   * El `PUT` a la URL prefirmada no pasa por el API. Enviar varios GB a través de FastAPI
   * causaría timeouts y reintentos que reempiezan desde cero.
   *
   * `machineModelId` va en el ticket: un video que nace sin equipo acaba invisible en la
   * biblioteca, que es el problema que motivó todo esto (D-055, D-060).
   */
  uploadVideo(file: File, machineModelId: string | null): Observable<UploadState> {
    return this.http
      .post<VideoUploadTicket>(`${this.base}/videos/upload-url`, {
        filename: file.name,
        size_bytes: file.size,
        machine_model_id: machineModelId,
      })
      .pipe(
        switchMap((ticket) =>
          concat(
            // Se emite el id ANTES de empezar a subir: es lo que permite cancelar y borrar el
            // asset huérfano que si no quedaría en `uploaded` sin fichero detrás.
            of<UploadState>({ progress: 0, videoAssetId: ticket.video_asset_id }),
            this.http
              .put(ticket.upload_url, file, {
                headers: { 'Content-Type': file.type || 'video/mp4' },
                reportProgress: true,
                observe: 'events',
              })
              .pipe(
                map((event: HttpEvent<unknown>): UploadState => {
                  if (event.type === HttpEventType.UploadProgress && event.total) {
                    return { progress: Math.round((event.loaded / event.total) * 100) };
                  }
                  if (event.type === HttpEventType.Response) {
                    return { progress: 100, videoAssetId: ticket.video_asset_id, done: true };
                  }
                  // Sent/ResponseHeader llegan al FINAL de la subida: devolver 0 aquí hacía que
                  // la barra saltara de 99 a 0 justo antes de completarse.
                  return { progress: -1 };
                }),
              ),
          ),
        ),
      );
  }
}
