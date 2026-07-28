import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../../agent/presentation/agent_fab.dart';
import '../../../core/theme/app_theme_extensions.dart';
import '../../../core/theme/design_tokens.dart';
import '../../../shared/errors/error_presenter.dart';
import '../../../shared/format/formatters.dart';
import '../../../shared/widgets/app_progress_bar.dart';
import '../../../shared/widgets/skeleton.dart';
import '../../../shared/widgets/skeletons/lesson_skeleton.dart';
import '../../../shared/widgets/status_view.dart';
import '../../../shared/widgets/tonal_pill.dart';
import '../data/lms_repository.dart';
import 'player/hls_player_view.dart';

/// Lección: video HLS, texto o documento, con el agente accesible en todo momento.
class LessonScreen extends ConsumerStatefulWidget {
  const LessonScreen({super.key, required this.lessonId, this.machineModelId});

  final String lessonId;
  final String? machineModelId;

  @override
  ConsumerState<LessonScreen> createState() => _LessonScreenState();
}

class _LessonScreenState extends ConsumerState<LessonScreen> {
  String? _accessToken;
  bool _tokenMissing = false;
  LessonProgress? _liveProgress;

  @override
  void initState() {
    super.initState();
    // El reproductor necesita el token para la petición del playlist (va en la query, D-049).
    // Si el keystore no lo devuelve, se marca explícitamente: antes esto dejaba un
    // "Loading video…" eterno sin diagnóstico posible.
    ref.read(tokenStorageProvider).readAccess().then((token) {
      if (mounted) {
        setState(() {
          _accessToken = token;
          _tokenMissing = token == null;
        });
      }
    });
  }

  void _reportProgress(double positionSeconds) {
    ref
        .read(lmsRepositoryProvider)
        .reportProgress(widget.lessonId, positionSeconds)
        .then((progress) {
      if (progress == null || !mounted) {
        return;
      }
      setState(() => _liveProgress = progress);

      // Al completarse, la ruta de aprendizaje cambia (puede desbloquear el módulo siguiente),
      // así que se invalida para que se recargue al volver atrás.
      if (progress.isCompleted && widget.machineModelId != null) {
        ref.invalidate(learningPathProvider(widget.machineModelId!));
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final lesson = ref.watch(lessonProvider(widget.lessonId));

    return Scaffold(
      appBar: AppBar(
        title: Text(
          lesson.valueOrNull?.title ?? 'Lesson',
          overflow: TextOverflow.ellipsis,
        ),
      ),
      floatingActionButton: widget.machineModelId == null
          ? null
          : AgentFab(
              machineModelId: widget.machineModelId!,
              machineName: null,
              lessonId: widget.lessonId,
            ),
      body: lesson.when(
        loading: () => const Padding(
          padding: EdgeInsets.all(AppSpacing.screenH),
          child: Skeleton(child: LessonSkeleton()),
        ),
        error: (error, _) => _LessonError(error: error),
        data: (detail) => _LessonBody(
          detail: detail,
          accessToken: _accessToken,
          tokenMissing: _tokenMissing,
          progress: _liveProgress ?? detail.progress,
          onProgress: _reportProgress,
        ),
      ),
    );
  }
}

class _LessonBody extends StatelessWidget {
  const _LessonBody({
    required this.detail,
    required this.accessToken,
    required this.tokenMissing,
    required this.progress,
    required this.onProgress,
  });

  final LessonDetail detail;
  final String? accessToken;
  final bool tokenMissing;
  final LessonProgress progress;
  final void Function(double) onProgress;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hlsUrl = detail.absoluteHlsUrl;

    return ListView(
      padding: const EdgeInsets.fromLTRB(0, 0, 0, 96),
      children: [
        if (detail.contentType == 'video')
          if (hlsUrl != null && accessToken != null)
            HlsPlayerView(
              masterUrl: hlsUrl,
              accessToken: accessToken!,
              startAtSeconds: progress.lastPositionSeconds,
              onProgress: onProgress,
            )
          else if (tokenMissing || hlsUrl == null)
            // Estado terminal, no de espera: sin token o sin playlist el video no va a llegar
            // nunca, y el spinner eterno era indistinguible de una carga lenta.
            AspectRatio(
              aspectRatio: 16 / 9,
              child: ColoredBox(
                color: theme.colorScheme.surfaceContainerHighest,
                child: Center(
                  child: StatusView.error(
                    title: 'The video is not available',
                    message: tokenMissing
                        ? 'Your session could not be read. Sign out and back in.'
                        : 'The video is still processing or was removed.',
                    compact: true,
                    icon: Icons.videocam_off_outlined,
                  ),
                ),
              ),
            )
          else
            AspectRatio(
              aspectRatio: 16 / 9,
              child: ColoredBox(
                color: theme.colorScheme.surfaceContainerHighest,
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const CircularProgressIndicator(),
                      const SizedBox(height: AppSpacing.md),
                      Text(
                        'Loading video…',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(detail.title, style: theme.textTheme.headlineSmall),
              const SizedBox(height: AppSpacing.md),

              // Fila de metadatos con datos que el modelo ya traía y no se mostraban: la duración
              // real del video (`durationSeconds`) y la fecha de finalización.
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  TonalPill(
                    label: switch (detail.contentType) {
                      'video' => 'Video',
                      'pdf' => 'Document',
                      _ => 'Reading',
                    },
                    icon: switch (detail.contentType) {
                      'video' => Icons.play_circle_outline,
                      'pdf' => Icons.description_outlined,
                      _ => Icons.article_outlined,
                    },
                  ),
                  if (detail.durationSeconds != null)
                    TonalPill(
                      label: durationLabel(detail.durationSeconds),
                      icon: Icons.schedule_outlined,
                    )
                  else if (detail.estimatedMinutes != null)
                    TonalPill(
                      label: minutesLabel(detail.estimatedMinutes),
                      icon: Icons.schedule_outlined,
                    ),
                  if (progress.isCompleted)
                    TonalPill(
                      label: completedAtLabel(progress.completedAt).isEmpty
                          ? 'Completed'
                          : 'Completed ${completedAtLabel(progress.completedAt)}',
                      icon: Icons.check_circle_outline,
                      foreground: context.semantic.onSuccessContainer,
                      background: context.semantic.successContainer,
                    ),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),

              if (!progress.isCompleted && progress.watchedPercent > 0) ...[
                AppProgressBar(
                  value: progress.watchedPercent / 100,
                  height: 6,
                  label: '${progress.watchedPercent.round()}%',
                ),
                const SizedBox(height: AppSpacing.lg),
              ],

              // Ancho de lectura acotado: en una tablet, un párrafo de 100 caracteres por línea se
              // lee mucho peor que uno de 70.
              if (detail.body != null)
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: AppSizes.maxReadWidth),
                  child: Text(detail.body!, style: theme.textTheme.bodyLarge),
                ),

              if (detail.documentUrl != null) ...[
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  onPressed: () {
                    // La URL prefirmada caduca; se abre en el visor del sistema. Se deja como
                    // pendiente integrar un visor de PDF en la app.
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('Document viewer not integrated yet.'),
                      ),
                    );
                  },
                  icon: const Icon(Icons.picture_as_pdf_outlined),
                  label: const Text('Open document'),
                ),
              ],

              // Una lección de texto se marca como vista al abrirla: no hay forma de medir
              // "cuánto" se leyó, y un progreso que nunca avanza es peor que uno generoso.
              if (detail.contentType != 'video' && !progress.isCompleted) ...[
                const SizedBox(height: 24),
                FilledButton.icon(
                  onPressed: () => onProgress(1),
                  icon: const Icon(Icons.check),
                  label: const Text('Mark as completed'),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _LessonError extends StatelessWidget {
  const _LessonError({required this.error});

  final Object error;

  @override
  Widget build(BuildContext context) {
    // Una lección bloqueada no es un fallo: es el prerrequisito funcionando. Tono de aviso, no de
    // error, y el mensaje dice qué hacer en lugar de solo qué pasó.
    final locked = error is LessonLockedException;

    return locked
        ? StatusView.locked(
            title: 'Lesson locked',
            message: (error as LessonLockedException).message,
            actions: [
              AppAction(
                label: 'Back to the training',
                icon: Icons.arrow_back,
                onPressed: () => Navigator.of(context).maybePop(),
              ),
            ],
          )
        : StatusView.error(
            title: 'Could not open the lesson',
            message: friendlyMessage(error),
            actions: [
              AppAction(
                label: 'Go back',
                icon: Icons.arrow_back,
                onPressed: () => Navigator.of(context).maybePop(),
              ),
            ],
          );
  }
}
