/**
 * Servicio del Agent Builder. Espejo de `app/modules/agent/router.py`.
 *
 * Los tipos viven en `core/models/api.models.ts`, no aquí: tenerlos duplicados en el servicio
 * hacía que TypeScript viese dos `KnowledgeDocument` distintos y el build fallara al pasar uno
 * donde se esperaba el otro. Una sola definición por entidad.
 *
 * Cuando el contrato se estabilice, generarlos desde el OpenAPI del backend:
 *   npx openapi-typescript http://localhost:8000/openapi.json -o src/app/core/models/api.d.ts
 */

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  AgentConfig,
  AgentRuntimeSettings,
  BasePromptRead,
  KnowledgeDocument,
  LlmProvider,
  PromptPreview,
  ProviderCredential,
  ProviderSpec,
  RetrievedChunk,
  ToolDefinition,
} from '../models/api.models';

export interface CredentialTestResult {
  ok: boolean;
  message: string;
  latency_ms: number | null;
}

@Injectable({ providedIn: 'root' })
export class AgentBuilderService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/agent`;

  // --- Introspección (D-053) ---------------------------------------------

  /** El prompt base del sistema, visible pero no editable (D-006). */
  basePrompt(): Observable<BasePromptRead> {
    return this.http.get<BasePromptRead>(`${this.base}/prompt`);
  }

  /** El system prompt final que recibiría el LLM con esta configuración. */
  previewPrompt(configId: string, machineModelId: string | null): Observable<PromptPreview> {
    return this.http.post<PromptPreview>(`${this.base}/configs/${configId}/preview-prompt`, {
      machine_model_id: machineModelId,
    });
  }

  /** Umbral de distancia y top_k reales del backend: fin de las copias hardcodeadas. */
  settings(): Observable<AgentRuntimeSettings> {
    return this.http.get<AgentRuntimeSettings>(`${this.base}/settings`);
  }

  // --- Proveedores y credenciales ------------------------------------------
  listProviders(): Observable<ProviderSpec[]> {
    return this.http.get<ProviderSpec[]>(`${this.base}/providers`);
  }

  listCredentials(): Observable<ProviderCredential[]> {
    return this.http.get<ProviderCredential[]>(`${this.base}/credentials`);
  }

  createCredential(payload: {
    provider: LlmProvider;
    label?: string;
    api_key: string;
    base_url?: string | null;
    is_active?: boolean;
  }): Observable<ProviderCredential> {
    return this.http.post<ProviderCredential>(`${this.base}/credentials`, payload);
  }

  /**
   * Comprueba la conectividad con una llamada mínima al proveedor.
   * Consume unos pocos tokens, pero evita descubrir una clave inválida en medio de una demo.
   */
  testCredential(id: string, modelName?: string): Observable<CredentialTestResult> {
    const query = modelName ? `?model_name=${encodeURIComponent(modelName)}` : '';
    return this.http.post<CredentialTestResult>(`${this.base}/credentials/${id}/test${query}`, {});
  }

  // --- Configuración de agentes --------------------------------------------
  listConfigs(): Observable<AgentConfig[]> {
    return this.http.get<AgentConfig[]>(`${this.base}/configs`);
  }

  createConfig(payload: Partial<AgentConfig>): Observable<AgentConfig> {
    return this.http.post<AgentConfig>(`${this.base}/configs`, payload);
  }

  updateConfig(id: string, payload: Partial<AgentConfig>): Observable<AgentConfig> {
    return this.http.patch<AgentConfig>(`${this.base}/configs/${id}`, payload);
  }

  // --- Base de conocimiento -------------------------------------------------
  listDocuments(machineModelId?: string): Observable<KnowledgeDocument[]> {
    const query = machineModelId ? `?machine_model_id=${machineModelId}` : '';
    return this.http.get<KnowledgeDocument[]>(`${this.base}/documents${query}`);
  }

  /** Devuelve 202: la indexación es asíncrona, hay que hacer polling de `status`. */
  createDocument(payload: {
    title: string;
    source_type: KnowledgeDocument['source_type'];
    machine_model_id?: string | null;
    lesson_id?: string | null;
    raw_text?: string;
    object_key?: string;
  }): Observable<KnowledgeDocument> {
    return this.http.post<KnowledgeDocument>(`${this.base}/documents`, payload);
  }

  reindexDocument(id: string): Observable<KnowledgeDocument> {
    return this.http.post<KnowledgeDocument>(`${this.base}/documents/${id}/reindex`, {});
  }

  /**
   * Inspector de recuperación: muestra qué fragmentos devuelve el RAG y con qué distancia, sin
   * gastar tokens del LLM. Es la herramienta de diagnóstico principal cuando el agente responde
   * mal.
   */
  retrievalTest(payload: {
    query: string;
    machine_model_id?: string | null;
    top_k?: number;
  }): Observable<RetrievedChunk[]> {
    return this.http.post<RetrievedChunk[]>(`${this.base}/retrieval-test`, payload);
  }

  // --- Tools ----------------------------------------------------------------
  listTools(): Observable<ToolDefinition[]> {
    return this.http.get<ToolDefinition[]>(`${this.base}/tools`);
  }

  createTool(
    payload: Partial<ToolDefinition> & { auth_secret?: string },
  ): Observable<ToolDefinition> {
    return this.http.post<ToolDefinition>(`${this.base}/tools`, payload);
  }

  /** Desactiva (no borra): la tabla de auditoría conserva la referencia. */
  deactivateTool(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/tools/${id}`);
  }
}
