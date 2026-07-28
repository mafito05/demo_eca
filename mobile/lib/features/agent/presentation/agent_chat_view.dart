import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/app_config.dart';
import '../../../core/providers.dart';
import '../../../core/theme/app_theme.dart';
import '../../../shared/errors/error_presenter.dart';
import '../../../core/theme/app_theme_extensions.dart';
import '../../../core/theme/design_tokens.dart';
import '../../../shared/widgets/code_badge.dart';
import '../../../shared/widgets/info_banner.dart';
import '../../../shared/widgets/skeleton.dart';
import '../../../shared/widgets/typing_indicator.dart';
import '../data/agent_socket.dart';
import '../../../shared/widgets/ai_head_icon.dart';
import 'widgets/source_chips.dart';
import 'widgets/suggestion_card.dart';

/// Mensaje tal como se pinta en el chat.
class ChatMessage {
  ChatMessage({
    required this.fromUser,
    required this.text,
    this.sources = const [],
    this.streaming = false,
    this.isError = false,
    this.latencyMs,
  });

  final bool fromUser;
  String text;
  List<AgentCitation> sources;
  bool streaming;
  final bool isError;
  int? latencyMs;
}

/// Cuerpo del chat con el agente, sin `Scaffold`.
///
/// Se extrajo del `AgentChatScreen` para que lo compartan los dos sitios donde vive el asistente: el
/// módulo **ECAHelp** del menú (con selector de equipo) y el chat contextual que se abre desde un
/// equipo o una lección. Duplicar la lógica de streaming en dos pantallas habría garantizado que
/// divergieran.
///
/// El estado vive en el `State` y no en un provider porque es efímero: al cerrar el chat la
/// conversación queda persistida en el backend y el hilo local no aporta nada. Lo que sí sobrevive es
/// el `conversation_id`, que gestiona el socket.
class AgentChatView extends ConsumerStatefulWidget {
  const AgentChatView({
    super.key,
    required this.machineModelId,
    this.lessonId,
    this.showEmptyStateHint = false,
  });

  final String? machineModelId;
  final String? lessonId;

  /// Muestra el aviso de alcance en el estado vacío. Se activa en ECAHelp, donde el usuario llega
  /// sin haber pasado por un equipo y conviene explicarle qué puede preguntar.
  final bool showEmptyStateHint;

  @override
  ConsumerState<AgentChatView> createState() => _AgentChatViewState();
}

class _AgentChatViewState extends ConsumerState<AgentChatView> {
  final List<ChatMessage> _messages = [];
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();

  StreamSubscription<AgentEvent>? _subscription;
  AgentSocket? _socket;
  bool _thinking = false;
  String? _connectionError;
  String _lastQuestion = '';
  PendingToolConfirmation? _pendingTool;

  @override
  void initState() {
    super.initState();
    _connect();
  }

  /// Crea el socket con el ciclo de vida atado a ESTE widget, no a un provider.
  ///
  /// El diseño anterior era un `FutureProvider.autoDispose` leído con `ref.read`: al no dejar
  /// ningún listener vivo, Riverpod lo autodisponía en cuanto el read retornaba — el dispose
  /// ganaba la carrera contra el `await` de leer el token del keystore, y el `ref.onDispose`
  /// tardío lanzaba el `StateError: cannot call onDispose after a provider was disposed` que se
  /// pintaba en el banner. Y aunque no lanzara, nada anclaba el provider: el socket recién
  /// conectado se cerraba solo (D-050).
  ///
  /// Aquí quien usa el socket es quien lo posee: se crea en `initState`, se cierra en `dispose`,
  /// y el `ValueKey` de ECAHelp que recrea el widget al cambiar de equipo recrea también la
  /// conexión — que es exactamente el comportamiento buscado.
  Future<void> _connect() async {
    try {
      final token = await ref.read(tokenStorageProvider).readAccess();
      if (!mounted) {
        return;
      }
      if (token == null) {
        setState(() => _connectionError = 'Your session expired. Sign in again.');
        return;
      }

      // Si es un reintento, la conexión anterior se cierra antes de crear la nueva.
      await _subscription?.cancel();
      _socket?.dispose();

      final socket = AgentSocket(wsUrl: AppConfig.agentWsUrl, accessToken: token);
      _socket = socket;
      _subscription = socket.connect().listen(_onEvent);
      setState(() => _connectionError = null);
    } catch (error) {
      if (mounted) {
        setState(() => _connectionError = friendlyMessage(error));
      }
    }
  }

  void _onEvent(AgentEvent event) {
    if (!mounted) {
      return;
    }

    setState(() {
      switch (event.type) {
        case AgentEventType.start:
          // Se abre la burbuja del asistente en cuanto empieza, para que el usuario vea que algo
          // ocurre antes de que llegue el primer token.
          _messages.add(ChatMessage(fromUser: false, text: '', streaming: true));

        case AgentEventType.sources:
          _patchLast((message) => message.sources = event.sources);

        case AgentEventType.token:
          _patchLast((message) => message.text += event.text);

        case AgentEventType.toolCall:
          _patchLast(
            (message) => message.text += '\n\n[running: ${event.data['tool_name']}]\n\n',
          );

        case AgentEventType.confirmationRequired:
          _patchLast((message) => message.streaming = false);
          _thinking = false;
          _pendingTool = PendingToolConfirmation.fromEvent(event);

        case AgentEventType.done:
          _patchLast((message) {
            message.streaming = false;
            message.latencyMs = event.data['latency_ms'] as int?;
          });
          _thinking = false;

        case AgentEventType.error:
          _patchLast((message) => message.streaming = false);
          _thinking = false;
          _messages.add(ChatMessage(fromUser: false, text: event.errorMessage, isError: true));

        case AgentEventType.conversation:
        case AgentEventType.toolResult:
        case AgentEventType.pong:
        case AgentEventType.unknown:
          break;
      }
    });

    _scrollToEnd();
  }

  void _patchLast(void Function(ChatMessage) update) {
    final last = _messages.isNotEmpty ? _messages.last : null;
    if (last != null && !last.fromUser) {
      update(last);
    }
  }

  void _scrollToEnd() {
    // Tras el frame: el ListView todavía no ha medido el contenido nuevo.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _send([String? preset]) {
    final text = (preset ?? _input.text).trim();
    final socket = _socket;
    if (text.isEmpty || socket == null || _thinking) {
      return;
    }

    setState(() {
      _messages.add(ChatMessage(fromUser: true, text: text));
      _thinking = true;
      _lastQuestion = text;
      _pendingTool = null;
      _input.clear();
    });

    socket.sendMessage(
      content: text,
      machineModelId: widget.machineModelId,
      lessonId: widget.lessonId,
    );
    _scrollToEnd();
  }

  void _approveTool() {
    final pending = _pendingTool;
    final socket = _socket;
    if (pending == null || socket == null) {
      return;
    }
    setState(() {
      _thinking = true;
      _pendingTool = null;
    });
    socket.approveTool(
      lastQuestion: _lastQuestion,
      toolName: pending.toolName,
      machineModelId: widget.machineModelId,
      lessonId: widget.lessonId,
    );
  }

  @override
  void dispose() {
    _subscription?.cancel();
    // El widget es el dueño del socket (D-050): si no se cierra aquí, cada cambio de equipo en
    // ECAHelp dejaría un WebSocket vivo con su timer de ping.
    _socket?.dispose();
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        if (_connectionError != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.md,
              AppSpacing.md,
              AppSpacing.md,
              0,
            ),
            child: InfoBanner(
              message: _connectionError!,
              tone: BannerTone.error,
              actionLabel: 'Retry',
              onAction: _connect,
            ),
          ),
        Expanded(
          child: _messages.isEmpty
              ? _EmptyState(
                  onPick: _send,
                  machineModelId: widget.machineModelId,
                  showHint: widget.showEmptyStateHint,
                )
              : ListView.builder(
                  controller: _scroll,
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  itemCount: _messages.length,
                  itemBuilder: (context, index) => _Bubble(message: _messages[index]),
                ),
        ),
        if (_pendingTool != null)
          _ToolConfirmation(
            pending: _pendingTool!,
            onApprove: _approveTool,
            onReject: () => setState(() => _pendingTool = null),
          ),
        _Composer(
          controller: _input,
          enabled: !_thinking && _socket != null,
          thinking: _thinking,
          onSend: _send,
        ),
      ],
    );
  }
}

class _EmptyState extends ConsumerWidget {
  const _EmptyState({
    required this.onPick,
    required this.machineModelId,
    required this.showHint,
  });

  final void Function(String) onPick;
  final String? machineModelId;
  final bool showHint;

  /// Fallback si el backend no responde: el estado vacío nunca debe quedar sin ejemplos. Las
  /// listas reales viven en `AgentConfig.suggested_questions` y se editan desde el panel (D-053).
  static const _offlineEquipmentExamples = [
    'What should I do if the unit shows an error code?',
    'How do I run the daily calibration routine?',
  ];

  static const _offlineGeneralExamples = [
    'What safety checks are required before operating equipment?',
    'How do I record a maintenance intervention?',
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final hasMachineContext = machineModelId != null;
    final suggestions = ref.watch(agentSuggestionsProvider(machineModelId));

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Align(
          child: Container(
            width: AppSizes.statusCircle,
            height: AppSizes.statusCircle,
            decoration: BoxDecoration(
              color: theme.colorScheme.primaryContainer,
              shape: BoxShape.circle,
            ),
            child: Center(
              child: AiHeadIcon(
                size: AppSizes.statusIcon,
                color: theme.colorScheme.onPrimaryContainer,
              ),
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.xl),
        Text(
          hasMachineContext
              ? 'Ask about how to operate this equipment'
              : 'Ask about equipment operation',
          style: theme.textTheme.titleMedium,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 8),
        Text(
          hasMachineContext
              ? 'Answers come from the equipment manual and cite the exact section. No clinical '
                  'guidance: that is the treating professional\'s call.'
              : 'Select a piece of equipment above to get answers from its manual with citations. '
                  'Without one, only general questions can be answered.',
          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: AppSpacing.xxl),
        ...switch (suggestions) {
          // Mientras cargan, dos tarjetas fantasma del tamaño real: sin salto de layout.
          AsyncLoading() => const [
            Skeleton(
              child: Column(
                children: [
                  SkeletonBox(height: 56, borderRadius: AppRadii.field),
                  SizedBox(height: AppSpacing.sm),
                  SkeletonBox(height: 56, borderRadius: AppRadii.field),
                ],
              ),
            ),
          ],
          AsyncValue(:final value?) => [
            for (final example in value.questions)
              SuggestionCard(question: example, onTap: () => onPick(example)),
          ],
          // Backend inalcanzable: ejemplos empaquetados. Peor que los configurados, mejor que nada.
          _ => [
            for (final example in hasMachineContext
                ? _offlineEquipmentExamples
                : _offlineGeneralExamples)
              SuggestionCard(question: example, onTap: () => onPick(example)),
          ],
        },
        if (showHint) ...[
          const SizedBox(height: 12),
          Text(
            'ECAHelp does not replace the equipment documentation or clinical judgement.',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ],
    );
  }
}

class _Bubble extends ConsumerWidget {
  const _Bubble({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final background = message.isError
        ? theme.colorScheme.errorContainer
        : message.fromUser
            ? theme.colorScheme.primaryContainer
            : theme.colorScheme.surfaceContainerHighest;

    // Las respuestas del manual son largas: al asistente se le da más ancho que al usuario.
    final maxWidth = MediaQuery.sizeOf(context).width * (message.fromUser ? 0.85 : 0.92);
    // Radios asimétricos: la esquina pegada al lado de quien habla queda casi recta. Es lo que hace
    // que un hilo se lea como conversación y no como una lista de cajas.
    final radius = message.fromUser
        ? const BorderRadius.only(
            topLeft: Radius.circular(18),
            topRight: Radius.circular(18),
            bottomLeft: Radius.circular(18),
            bottomRight: Radius.circular(4),
          )
        : const BorderRadius.only(
            topLeft: Radius.circular(18),
            topRight: Radius.circular(18),
            bottomLeft: Radius.circular(4),
            bottomRight: Radius.circular(18),
          );

    return Align(
      alignment: message.fromUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(maxWidth: maxWidth),
        margin: const EdgeInsets.only(bottom: AppSpacing.md),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.md,
        ),
        decoration: BoxDecoration(color: background, borderRadius: radius),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!message.fromUser && !message.isError) ...[
              Row(
                children: [
                  AiHeadIcon(size: 15, color: theme.colorScheme.primary),
                  const SizedBox(width: AppSpacing.xs + 2),
                  Text(
                    'ECAHelp',
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.primary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
            ],

            // Puntos animados en lugar del literal de espera: un texto fijo durante varios
            // segundos no comunica actividad, parece que la respuesta ya llegó y dice eso.
            if (message.text.isEmpty && message.streaming)
              const TypingIndicator()
            else
              Text(message.text, style: theme.textTheme.bodyMedium),

            if (message.sources.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.md),
              Divider(height: 1, color: theme.colorScheme.outlineVariant),
              const SizedBox(height: AppSpacing.md),
              SourceChips(
                sources: message.sources,
                maxDistance: ref
                    .watch(agentSettingsProvider)
                    .valueOrNull
                    ?.ragMaxDistance,
              ),
            ],

            // Latencia solo en depuración: a un técnico junto a la máquina no le aporta nada, y
            // ocupaba una línea bajo cada respuesta.
            if (kDebugMode && message.latencyMs != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                '${message.latencyMs} ms',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Diálogo de confirmación de una herramienta con efectos secundarios.
///
/// El backend **detiene el turno** y no ejecuta nada hasta que el usuario aprueba: un modelo no debe
/// poder disparar acciones sobre sistemas externos por su cuenta.
class _ToolConfirmation extends StatelessWidget {
  const _ToolConfirmation({
    required this.pending,
    required this.onApprove,
    required this.onReject,
  });

  final PendingToolConfirmation pending;
  final VoidCallback onApprove;
  final VoidCallback onReject;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final semantic = context.semantic;

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: semantic.warningContainer,
        borderRadius: AppRadii.card,
        border: Border.all(color: semantic.warning.withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(Icons.pan_tool_outlined, size: 18, color: semantic.onWarningContainer),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  'Authorisation needed',
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: semantic.onWarningContainer,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            pending.description,
            style: theme.textTheme.bodySmall?.copyWith(color: semantic.onWarningContainer),
          ),
          const SizedBox(height: AppSpacing.sm),
          Align(
            alignment: Alignment.centerLeft,
            child: CodeBadge(pending.toolName, tone: semantic.onWarningContainer, dense: true),
          ),
          if (pending.arguments.isNotEmpty)
            // Colapsado: los argumentos en crudo son para auditar, no para leer cada vez.
            Theme(
              data: theme.copyWith(dividerColor: Colors.transparent),
              child: ExpansionTile(
                tilePadding: EdgeInsets.zero,
                childrenPadding: const EdgeInsets.only(bottom: AppSpacing.sm),
                title: Text(
                  'Parameters',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: semantic.onWarningContainer,
                  ),
                ),
                iconColor: semantic.onWarningContainer,
                collapsedIconColor: semantic.onWarningContainer,
                children: [
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      '${pending.arguments}',
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: semantic.onWarningContainer,
                        fontFamily: AppTheme.monoFamily,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: AppSpacing.md),
          FilledButton.icon(
            onPressed: onApprove,
            icon: const Icon(Icons.check),
            label: const Text('Authorise'),
          ),
          const SizedBox(height: AppSpacing.sm),
          TextButton(onPressed: onReject, child: const Text('Do not run it')),
        ],
      ),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.enabled,
    required this.thinking,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool enabled;
  final bool thinking;
  final void Function() onSend;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    // Superficie elevada con divisoria: separa el compositor del hilo, que si no parece un mensaje
    // más de la lista.
    return DecoratedBox(
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainer,
        border: Border(top: BorderSide(color: theme.colorScheme.outlineVariant)),
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.md,
            AppSpacing.md,
            AppSpacing.md,
            AppSpacing.md,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  enabled: enabled,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => onSend(),
                  maxLines: 4,
                  minLines: 1,
                  decoration: InputDecoration(
                    hintText: 'Type your question…',
                    // Radio mayor que el del tema: junto a un botón circular, un campo muy
                    // cuadrado desentona.
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppRadii.xxl),
                      borderSide: BorderSide.none,
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppRadii.xxl),
                      borderSide: BorderSide.none,
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppRadii.xxl),
                      borderSide: BorderSide(color: theme.colorScheme.primary, width: 2),
                    ),
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.xl,
                      vertical: 14,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              SizedBox(
                width: AppSizes.minTouch,
                height: AppSizes.minTouch,
                child: IconButton.filled(
                  onPressed: enabled ? onSend : null,
                  tooltip: 'Send',
                  icon: thinking
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.arrow_upward_rounded),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
