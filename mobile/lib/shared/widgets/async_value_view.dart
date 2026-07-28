/// Mapea un `AsyncValue` a skeleton / error / dato, en un solo sitio.
///
/// Elimina de golpe los ocho `CircularProgressIndicator` pelados que había repartidos por las
/// pantallas, y garantiza que el error siempre pasa por `friendlyMessage` — hoy hay al menos un
/// sitio (`machine_screen.dart`) que pinta el `$error` crudo de Dio a pantalla completa.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../errors/error_presenter.dart';
import 'skeleton.dart';
import 'status_view.dart';

class AsyncValueView<T> extends StatelessWidget {
  const AsyncValueView({
    required this.value,
    required this.data,
    required this.skeleton,
    super.key,
    this.onRetry,
    this.errorTitle,
    this.sliver = false,
  });

  final AsyncValue<T> value;
  final Widget Function(T data) data;

  /// Placeholder de carga. Se pide explícitamente en lugar de dar uno genérico: un skeleton que no
  /// se parece a lo que va a aparecer produce un salto de layout, que se lee como un fallo.
  final Widget Function() skeleton;

  final VoidCallback? onRetry;
  final String? errorTitle;

  /// Si el consumidor es un `CustomScrollView`, los tres estados deben ser slivers.
  final bool sliver;

  @override
  Widget build(BuildContext context) => value.when(
    data: (value) => data(value),
    loading: () => _wrap(Skeleton(child: skeleton())),
    error: (error, _) => _error(error),
  );

  Widget _wrap(Widget child) => sliver ? SliverToBoxAdapter(child: child) : child;

  Widget _error(Object error) {
    final offline = isOffline(error);
    final title = errorTitle ?? (offline ? 'No connection' : 'Something went wrong');
    final actions = onRetry == null
        ? const <AppAction>[]
        : [AppAction(label: 'Try again', icon: Icons.refresh, onPressed: onRetry!)];

    if (sliver) {
      return StatusView.sliver(
        icon: offline ? Icons.cloud_off_outlined : Icons.error_outline,
        title: title,
        message: friendlyMessage(error),
        actions: actions,
        tone: StatusTone.error,
      );
    }
    return StatusView.error(
      title: title,
      message: friendlyMessage(error),
      actions: actions,
      icon: offline ? Icons.cloud_off_outlined : Icons.error_outline,
    );
  }
}
