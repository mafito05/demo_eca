/**
 * Tipos del API. Espejo de los schemas de Pydantic.
 *
 * Se escriben a mano por ahora porque son pocos y así el panel es legible sin abrir el
 * backend. En cuanto el contrato se estabilice conviene generarlos:
 *
 *   npx openapi-typescript http://localhost:8000/openapi.json -o src/app/core/models/api.d.ts
 *
 * Mantenerlos a mano de forma permanente los desincroniza en una semana.
 */

export type UserRole = 'superadmin' | 'admin' | 'trainee';
export type PublishStatus = 'draft' | 'published' | 'archived';
export type Specialty = 'urologia' | 'trauma' | 'cardiologia' | 'neurocirugia' | 'otro';
export type LlmProvider = 'openai' | 'anthropic' | 'google' | 'grok' | 'deepseek';
export type IngestStatus = 'pending' | 'processing' | 'indexed' | 'failed';
export type VideoStatus = 'uploaded' | 'queued' | 'processing' | 'ready' | 'failed';
export type LessonContentType = 'video' | 'pdf' | 'text';
export type ProgressStatus = 'not_started' | 'in_progress' | 'completed';
export type DocumentSourceType = 'manual_pdf' | 'video_transcript' | 'raw_text';

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  specialty: string | null;
  institution: string | null;
  is_demo: boolean;
}

export interface Machine {
  id: string;
  code: string;
  name: string;
  manufacturer: string | null;
  specialty: Specialty;
  description: string | null;
  status: PublishStatus;
  qr_token: string;
  /** Progreso del usuario autenticado. Agregado por el backend, no es un N+1 del cliente. */
  lessons_count: number;
  completed_lessons: number;
  progress_percent: number;
}

export interface QrExport {
  machine_code: string;
  machine_name: string;
  specialty: string;
  qr_token: string;
  qr_url: string;
  qr_custom_scheme: string;
  png_endpoint: string;
  svg_endpoint: string;
}

export interface ProviderSpec {
  key: LlmProvider;
  display_name: string;
  suggested_models: string[];
  supports_tools: boolean;
  supports_streaming: boolean;
  requires_base_url: boolean;
  default_base_url: string | null;
  api_key_url: string | null;
}

export interface ProviderCredential {
  id: string;
  provider: LlmProvider;
  label: string;
  /** El backend nunca devuelve la clave en claro, ni al superadmin. */
  api_key_masked: string;
  base_url: string | null;
  is_active: boolean;
  last_checked_at: string | null;
  last_check_ok: boolean | null;
  last_check_error: string | null;
}

export interface AgentConfig {
  id: string;
  name: string;
  description: string | null;
  provider: LlmProvider;
  model_name: string;
  temperature: number;
  max_tokens: number;
  /** Se AÑADE al prompt base de seguridad; no lo sustituye (D-006). */
  system_prompt_extra: string | null;
  rag_enabled: boolean;
  rag_top_k: number;
  tools_enabled: boolean;
  machine_model_id: string | null;
  is_default: boolean;
  is_active: boolean;
  /** Preguntas de ejemplo del chat de la app. Vacío = las genéricas del backend (D-053). */
  suggested_questions: string[];
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  source_type: 'manual_pdf' | 'video_transcript' | 'raw_text';
  machine_model_id: string | null;
  lesson_id: string | null;
  status: IngestStatus;
  chunk_count: number;
  error_message: string | null;
  indexed_at: string | null;
  created_at: string;
}

export interface RetrievedChunk {
  document_id: string;
  document_title: string;
  citation: string;
  distance: number;
  content: string;
}

export interface ToolDefinition {
  id: string;
  name: string;
  description: string;
  http_method: string;
  url_template: string;
  parameters_schema: Record<string, unknown>;
  auth_type: 'none' | 'bearer' | 'api_key_header' | 'basic';
  auth_secret_masked: string | null;
  requires_confirmation: boolean;
  timeout_seconds: number;
  machine_model_id: string | null;
  is_active: boolean;
}

export interface TrainingModule {
  id: string;
  machine_model_id: string;
  title: string;
  description: string | null;
  order_index: number;
  requires_previous: boolean;
  status: PublishStatus;
}

export interface Lesson {
  id: string;
  training_module_id: string;
  title: string;
  content_type: LessonContentType;
  order_index: number;
  video_asset_id: string | null;
  estimated_minutes: number | null;
  status: PublishStatus;
}

export interface VideoAsset {
  id: string;
  original_filename: string;
  status: VideoStatus;
  duration_seconds: number | null;
  renditions: { name: string; playlist_key: string; width: number; height: number }[];
  error_message: string | null;
  attempts: number;
}

export interface VideoAssetListItem {
  id: string;
  original_filename: string;
  status: VideoStatus;
  duration_seconds: number | null;
  error_message: string | null;
  attempts: number;
  created_at: string;
  /** Títulos de las lecciones que lo usan. Vacío = huérfano, se puede borrar. */
  used_by_lessons: string[];
}

export interface VideoUploadTicket {
  video_asset_id: string;
  upload_url: string;
  object_key: string;
  expires_in_seconds: number;
}

export interface LearningPath {
  machine_model_id: string;
  machine_name: string;
  machine_code: string;
  total_lessons: number;
  completed_lessons: number;
  progress_percent: number;
  modules: {
    id: string;
    title: string;
    description: string | null;
    order_index: number;
    locked: boolean;
    completed_lessons: number;
    total_lessons: number;
    lessons: {
      id: string;
      title: string;
      content_type: LessonContentType;
      order_index: number;
      estimated_minutes: number | null;
      has_video: boolean;
      video_ready: boolean;
      progress: {
        status: ProgressStatus;
        last_position_seconds: number;
        watched_percent: number;
        completed_at: string | null;
      };
    }[];
  }[];
}

/** Eventos que emite el WebSocket del agente. Espejo de `AgentEvent` en service.py. */
export type AgentEventType =
  | 'conversation'
  | 'start'
  | 'sources'
  | 'token'
  | 'tool_call'
  | 'tool_result'
  | 'confirmation_required'
  | 'done'
  | 'error'
  | 'pong';

export interface AgentEvent {
  type: AgentEventType;
  data: Record<string, any>;
}

export interface AgentSource {
  label: string;
  document_id: string;
  document_title: string;
  citation: string;
  distance: number;
  page?: number;
  timestamp?: string;
}

// =============================================================================
//  Dashboard (GET /stats/overview)
// =============================================================================
// Espejo de `backend/app/modules/stats/schemas.py`. Dos reglas del contrato que hay que
// respetar al pintar, o el panel dirá cosas falsas:
//
// 1. `| null` significa "no hay datos para calcularlo", NUNCA cero. Un 0 % de respuestas con
//    fuente sobre cero respuestas sería una afirmación inventada. Se pinta `—`, no `0`.
// 2. Las fechas llegan como `YYYY-MM-DD` y se pintan tal cual. Pasarlas por `new Date(...)` las
//    interpreta como medianoche UTC, y en husos negativos el último bucket "salta a mañana".

export type ActionSeverity = 'info' | 'warning' | 'critical';

export interface SpecialtyCount {
  specialty: Specialty;
  total: number;
  published: number;
}

export interface MachineCounters {
  total: number;
  draft: number;
  published: number;
  archived: number;
  published_without_content: number;
  by_specialty: SpecialtyCount[];
}

export interface ModuleCounters {
  total: number;
  draft: number;
  published: number;
  archived: number;
}

export interface LessonCounters {
  total: number;
  draft: number;
  published: number;
  archived: number;
  video: number;
  pdf: number;
  text: number;
  video_without_asset: number;
  estimated_minutes_total: number;
}

export interface VideoCounters {
  total: number;
  uploaded: number;
  queued: number;
  processing: number;
  ready: number;
  failed: number;
  ready_minutes: number | null;
  total_size_mb: number | null;
}

export interface ContentStats {
  machines: MachineCounters;
  modules: ModuleCounters;
  lessons: LessonCounters;
  videos: VideoCounters;
}

export interface SourceTypeCount {
  source_type: DocumentSourceType;
  total: number;
}

export interface KnowledgeStats {
  documents_total: number;
  documents_pending: number;
  documents_processing: number;
  documents_indexed: number;
  documents_failed: number;
  documents_global: number;
  documents_by_source_type: SourceTypeCount[];
  chunks_total: number;
  chunks_global: number;
  /** Puede discrepar de `chunks_total`: la discrepancia ES la señal de una ingesta a medias. */
  declared_chunk_count_total: number;
  embedding_models: string[];
  average_chunks_per_indexed_document: number | null;
  last_indexed_at: string | null;
}

export interface DailyActivity {
  day: string;
  conversations: number;
  messages: number;
}

export interface ProviderUsage {
  provider: string;
  assistant_messages: number;
  total_tokens: number;
  avg_latency_ms: number | null;
}

export interface LatencyStats {
  /** Siempre presente. Si es 0, el resto es null y el tile debe rotularlo o esconderse. */
  sample_size: number;
  p50_ms: number | null;
  p95_ms: number | null;
  avg_ms: number | null;
  max_ms: number | null;
}

export interface AgentActivityStats {
  window_days: number;
  window_start: string;
  window_end: string;
  /** El tráfico de la cuenta demo SÍ cuenta aquí: sus tokens y latencia son coste real. */
  includes_demo_traffic: boolean;
  conversations_total: number;
  conversations_in_window: number;
  conversations_archived: number;
  conversations_with_machine_context: number;
  distinct_users_in_window: number;
  messages_total: number;
  messages_in_window: number;
  assistant_messages_in_window: number;
  prompt_tokens_total: number;
  completion_tokens_total: number;
  tokens_total: number;
  grounded_assistant_messages: number;
  grounded_answer_percent: number | null;
  tool_invocations_in_window: number;
  latency: LatencyStats;
  by_provider: ProviderUsage[];
  /** Exactamente `window_days` entradas contiguas. Los días sin actividad vienen a cero. */
  daily: DailyActivity[];
}

export interface SystemHealthStats {
  provider_credentials_total: number;
  provider_credentials_active: number;
  provider_credentials_failing_check: number;
  provider_credentials_never_checked: number;
  agent_configs_total: number;
  agent_configs_active: number;
  has_default_agent_config: boolean;
  tools_total: number;
  tools_active: number;
  tool_invocations_in_window: number;
  tool_invocation_errors_in_window: number;
  tool_error_percent: number | null;
  videos_failed: number;
  videos_stuck_processing: number;
  documents_failed: number;
  documents_stuck_processing: number;
}

export interface TrainingStats {
  /** Las cuentas demo se EXCLUYEN aquí: el login demo es compartido. */
  excludes_demo_users: boolean;
  users_total: number;
  users_active: number;
  trainees_total: number;
  users_logged_in_in_window: number;
  progress_rows_total: number;
  lessons_in_progress: number;
  lessons_completed: number;
  lessons_completed_in_window: number;
  average_watched_percent: number | null;
  completion_percent: number | null;
  active_users_in_window: number;
}

export interface PendingAction {
  code: string;
  severity: ActionSeverity;
  count: number;
  message: string;
  resource: string | null;
}

export interface RecentConversation {
  id: string;
  created_at: string;
  title: string | null;
  user_name: string;
  machine_code: string | null;
  machine_name: string | null;
  message_count: number;
  p50_ms: number | null;
  provider: string | null;
}

export interface StatsOverview {
  generated_at: string;
  window_days: number;
  content: ContentStats;
  knowledge: KnowledgeStats;
  agent: AgentActivityStats;
  health: SystemHealthStats;
  training: TrainingStats;
  pending_actions: PendingAction[];
  recent_conversations: RecentConversation[];
}

// =============================================================================
//  Autoría del LMS (GET /lms/machines/{id}/authoring) — D-052
// =============================================================================
export interface LessonAuthoring {
  id: string;
  title: string;
  content_type: LessonContentType;
  order_index: number;
  video_asset_id: string | null;
  video_status: VideoStatus | null;
  document_key: string | null;
  body: string | null;
  estimated_minutes: number | null;
  status: PublishStatus;
}

export interface ModuleAuthoring {
  id: string;
  title: string;
  description: string | null;
  order_index: number;
  requires_previous: boolean;
  status: PublishStatus;
  lessons: LessonAuthoring[];
}

export interface AuthoringTree {
  machine_model_id: string;
  machine_code: string;
  machine_name: string;
  machine_status: PublishStatus;
  modules: ModuleAuthoring[];
}

// =============================================================================
//  Introspección del agente (D-053)
// =============================================================================
export interface SuggestedQuestions {
  questions: string[];
  has_machine_context: boolean;
  source: 'config' | 'default';
}

export interface AgentRuntimeSettings {
  rag_max_distance: number;
  rag_top_k: number;
}

export interface BasePromptRead {
  base_prompt: string;
  machine_context_template: string;
  no_context_notice: string;
}

export interface PromptPreview {
  prompt: string;
  includes_machine_context: boolean;
  note: string;
}
