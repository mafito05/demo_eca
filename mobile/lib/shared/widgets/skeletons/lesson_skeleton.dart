/// Placeholder de una lección: bloque 16:9, título, pills y párrafo.
library;

import 'package:flutter/material.dart';

import '../../../core/theme/design_tokens.dart';
import '../skeleton.dart';

class LessonSkeleton extends StatelessWidget {
  const LessonSkeleton({super.key});

  @override
  Widget build(BuildContext context) => const Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      AspectRatio(
        aspectRatio: 16 / 9,
        child: SkeletonBox(borderRadius: AppRadii.card),
      ),
      SizedBox(height: AppSpacing.xl),
      SkeletonLine(widthFactor: 0.7, height: 22),
      SizedBox(height: AppSpacing.lg),
      Row(
        children: [
          SkeletonBox(width: 74, height: 26, borderRadius: AppRadii.bar),
          SizedBox(width: AppSpacing.sm),
          SkeletonBox(width: 62, height: 26, borderRadius: AppRadii.bar),
        ],
      ),
      SizedBox(height: AppSpacing.xl),
      // Anchos decrecientes: es como acaba un párrafo de verdad.
      SkeletonLine(height: 13),
      SizedBox(height: AppSpacing.md),
      SkeletonLine(height: 13),
      SizedBox(height: AppSpacing.md),
      SkeletonLine(widthFactor: 0.92, height: 13),
      SizedBox(height: AppSpacing.md),
      SkeletonLine(widthFactor: 0.6, height: 13),
    ],
  );
}
