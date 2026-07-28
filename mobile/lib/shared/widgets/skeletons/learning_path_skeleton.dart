/// Placeholder de la ruta de aprendizaje.
///
/// Imita dos tarjetas de módulo con sus filas de lección. Se usa dentro de un `Skeleton` padre, que
/// es quien aporta el `AnimationController` compartido.
library;

import 'package:flutter/material.dart';

import '../../../core/theme/design_tokens.dart';
import '../skeleton.dart';

class LearningPathSkeleton extends StatelessWidget {
  const LearningPathSkeleton({super.key, this.modules = 2, this.lessonsPerModule = 3});

  final int modules;
  final int lessonsPerModule;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      for (var index = 0; index < modules; index++) ...[
        _ModuleSkeleton(lessons: lessonsPerModule),
        const SizedBox(height: AppSpacing.md),
      ],
    ],
  );
}

class _ModuleSkeleton extends StatelessWidget {
  const _ModuleSkeleton({required this.lessons});

  final int lessons;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(AppSpacing.cardPad),
    decoration: BoxDecoration(
      border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      borderRadius: AppRadii.card,
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Row(
          children: [
            SkeletonCircle(size: 30),
            SizedBox(width: AppSpacing.md),
            Expanded(child: SkeletonLine(widthFactor: 0.55, height: 15)),
            SizedBox(width: AppSpacing.md),
            SkeletonBox(width: 32, height: 12),
          ],
        ),
        const SizedBox(height: AppSpacing.lg),
        const SkeletonBox(height: 5, borderRadius: AppRadii.bar),
        const SizedBox(height: AppSpacing.lg),
        for (var index = 0; index < lessons; index++) ...[
          Row(
            children: [
              const SkeletonCircle(size: 32),
              const SizedBox(width: AppSpacing.md),
              // Anchos alternos: si todas las filas miden lo mismo parece una tabla, no una lista.
              Expanded(child: SkeletonLine(widthFactor: index.isEven ? 0.7 : 0.5, height: 13)),
            ],
          ),
          if (index < lessons - 1) const SizedBox(height: AppSpacing.lg),
        ],
      ],
    ),
  );
}
