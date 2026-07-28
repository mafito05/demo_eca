import 'package:demoeca_app/features/lms/data/lms_repository.dart';
import 'package:demoeca_app/features/machine/data/machine_repository.dart';
import 'package:flutter_test/flutter_test.dart';

/// Deserialización de las respuestas del API.
///
/// Los payloads de estos tests están copiados de respuestas reales del backend. Si el contrato
/// cambia, estos tests fallan antes de que el fallo aparezca como una pantalla en blanco en el
/// móvil.
void main() {
  group('ResolvedMachine', () {
    test('mapea la respuesta del resolver de QR', () {
      final machine = ResolvedMachine.fromJson({
        'machine_model_id': '85759683-0d40-4746-b2cc-0f9554bae504',
        'code': 'URO-LITHO-3000',
        'name': 'Litotrictor Uro-Litho 3000',
        'specialty': 'urologia',
        'description': 'Litotrictor extracorpóreo por ondas de choque.',
        'modules_count': 2,
      });

      expect(machine.machineModelId, '85759683-0d40-4746-b2cc-0f9554bae504');
      expect(machine.code, 'URO-LITHO-3000');
      expect(machine.modulesCount, 2);
    });

    test('acepta descripción nula', () {
      final machine = ResolvedMachine.fromJson({
        'machine_model_id': 'x',
        'code': 'C',
        'name': 'N',
        'specialty': 'otro',
        'description': null,
        'modules_count': 0,
      });

      expect(machine.description, isNull);
    });
  });

  group('LessonProgress', () {
    LessonProgress build(String status, {double percent = 42}) => LessonProgress.fromJson({
          'status': status,
          'last_position_seconds': 5,
          'watched_percent': percent,
          'completed_at': status == 'completed' ? '2026-07-26T00:36:01.006143Z' : null,
        });

    test('distingue no empezada, en curso y completada', () {
      expect(build('not_started').isStarted, isFalse);
      expect(build('in_progress').isStarted, isTrue);
      expect(build('in_progress').isCompleted, isFalse);
      expect(build('completed').isCompleted, isTrue);
    });

    test('acepta enteros donde el backend puede enviar enteros o decimales', () {
      // `watched_percent` llega como 100 (int) cuando es exacto y como 95.83 (double) si no.
      final entero = LessonProgress.fromJson({
        'status': 'completed',
        'last_position_seconds': 12,
        'watched_percent': 100,
        'completed_at': null,
      });
      expect(entero.watchedPercent, 100.0);
      expect(entero.lastPositionSeconds, 12.0);
    });
  });

  group('LessonDetail', () {
    test('una lección de video expone su URL absoluta de HLS', () {
      final lesson = LessonDetail.fromJson({
        'id': 'l1',
        'title': 'Purga del circuito',
        'content_type': 'video',
        'body': null,
        'duration_seconds': 12.0,
        'hls_master_url': '/api/v1/lms/videos/v1/hls/master.m3u8',
        'document_url': null,
        'estimated_minutes': 1,
        'progress': {
          'status': 'not_started',
          'last_position_seconds': 0,
          'watched_percent': 0,
          'completed_at': null,
        },
      });

      expect(lesson.absoluteHlsUrl, startsWith('http'));
      expect(lesson.absoluteHlsUrl, endsWith('/api/v1/lms/videos/v1/hls/master.m3u8'));
      expect(lesson.durationSeconds, 12.0);
    });

    test('una lección de texto no tiene URL de video', () {
      final lesson = LessonDetail.fromJson({
        'id': 'l2',
        'title': 'Conexión y verificaciones previas',
        'content_type': 'text',
        'body': 'Contenido de la lección.',
        'duration_seconds': null,
        'hls_master_url': null,
        'document_url': null,
        'estimated_minutes': 8,
        'progress': {
          'status': 'not_started',
          'last_position_seconds': 0,
          'watched_percent': 0,
          'completed_at': null,
        },
      });

      expect(lesson.absoluteHlsUrl, isNull);
      expect(lesson.body, isNotNull);
    });
  });

  group('LearningPath', () {
    test('mapea módulos, bloqueo y progreso', () {
      final path = LearningPath.fromJson({
        'machine_model_id': 'm1',
        'machine_name': 'Litotrictor Uro-Litho 3000',
        'machine_code': 'URO-LITHO-3000',
        'total_lessons': 5,
        'completed_lessons': 1,
        'progress_percent': 20.0,
        'modules': [
          {
            'id': 'mod1',
            'title': 'Preparación y puesta en marcha',
            'description': null,
            'order_index': 0,
            'locked': false,
            'completed_lessons': 1,
            'total_lessons': 3,
            'lessons': [
              {
                'id': 'l1',
                'title': 'Purga del circuito (video)',
                'content_type': 'video',
                'order_index': 1,
                'estimated_minutes': 1,
                'has_video': true,
                'video_ready': true,
                'progress': {
                  'status': 'completed',
                  'last_position_seconds': 11.5,
                  'watched_percent': 95.8,
                  'completed_at': '2026-07-26T00:36:01.006143Z',
                },
              },
            ],
          },
          {
            'id': 'mod2',
            'title': 'Calibración y mantenimiento',
            'description': null,
            'order_index': 1,
            'locked': true,
            'completed_lessons': 0,
            'total_lessons': 2,
            'lessons': const [],
          },
        ],
      });

      expect(path.modules, hasLength(2));
      expect(path.progressPercent, 20.0);
      expect(path.modules.first.locked, isFalse);
      expect(path.modules.last.locked, isTrue);
      expect(path.modules.first.lessons.first.progress.isCompleted, isTrue);
    });

    test('un video en proceso se marca como no listo', () {
      final module = PathModule.fromJson({
        'id': 'mod1',
        'title': 'Módulo',
        'description': null,
        'locked': false,
        'completed_lessons': 0,
        'total_lessons': 1,
        'lessons': [
          {
            'id': 'l1',
            'title': 'Lección con video procesándose',
            'content_type': 'video',
            'order_index': 0,
            'estimated_minutes': null,
            'has_video': true,
            'video_ready': false,
            'progress': {
              'status': 'not_started',
              'last_position_seconds': 0,
              'watched_percent': 0,
              'completed_at': null,
            },
          },
        ],
      });

      expect(module.lessons.first.hasVideo, isTrue);
      expect(module.lessons.first.videoReady, isFalse);
    });
  });
}
