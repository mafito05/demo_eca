/// Placeholder del catálogo mientras carga.
///
/// Imita la forma real de la lista (cabecera de sección + tarjetas con avatar y dos líneas) en lugar
/// de un spinner centrado. La diferencia práctica: cuando llegan los datos no hay salto de layout,
/// porque el hueco ya tenía el tamaño correcto.
library;

import 'package:flutter/material.dart';

import '../../../core/theme/design_tokens.dart';
import '../skeleton.dart';

class CatalogSkeleton extends StatelessWidget {
  const CatalogSkeleton({super.key, this.sections = 2, this.cardsPerSection = 3});

  final int sections;
  final int cardsPerSection;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(
      AppSpacing.screenH,
      AppSpacing.lg,
      AppSpacing.screenH,
      0,
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Fila de chips de filtro.
        Row(
          children: [
            for (var index = 0; index < 3; index++) ...[
              SkeletonBox(width: 70 + index * 14, height: 32, borderRadius: AppRadii.bar),
              const SizedBox(width: AppSpacing.sm),
            ],
          ],
        ),
        for (var section = 0; section < sections; section++) ...[
          const SizedBox(height: AppSpacing.xxl),
          const SkeletonBox(width: 90, height: 10),
          const SizedBox(height: AppSpacing.md),
          for (var card = 0; card < cardsPerSection; card++) ...[
            const _CardSkeleton(),
            const SizedBox(height: AppSpacing.sm),
          ],
        ],
      ],
    ),
  );
}

class _CardSkeleton extends StatelessWidget {
  const _CardSkeleton();

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(AppSpacing.cardPad),
    decoration: BoxDecoration(
      border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      borderRadius: AppRadii.card,
    ),
    child: const Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SkeletonBox(
          width: AppSizes.specialtyTile,
          height: AppSizes.specialtyTile,
          borderRadius: BorderRadius.all(Radius.circular(13)),
        ),
        SizedBox(width: AppSpacing.lg),
        // Anchos desiguales: líneas todas iguales parecen una tabla, no un párrafo.
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SkeletonLine(widthFactor: 0.62, height: 15),
              SizedBox(height: AppSpacing.sm),
              SkeletonLine(widthFactor: 0.4, height: 11),
              SizedBox(height: AppSpacing.sm),
              SkeletonLine(widthFactor: 0.85, height: 11),
            ],
          ),
        ),
      ],
    ),
  );
}
