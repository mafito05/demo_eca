import '../../../core/config/app_config.dart';
import '../../../core/network/api_client.dart';

class LessonProgress {
  const LessonProgress({
    required this.status,
    required this.lastPositionSeconds,
    required this.watchedPercent,
    this.completedAt,
  });

  final String status;
  final double lastPositionSeconds;
  final double watchedPercent;
  final String? completedAt;

  bool get isCompleted => status == 'completed';
  bool get isStarted => status != 'not_started';

  factory LessonProgress.fromJson(Map<String, dynamic> json) => LessonProgress(
        status: json['status'] as String,
        lastPositionSeconds: (json['last_position_seconds'] as num).toDouble(),
        watchedPercent: (json['watched_percent'] as num).toDouble(),
        completedAt: json['completed_at'] as String?,
      );
}

class PathLesson {
  const PathLesson({
    required this.id,
    required this.title,
    required this.contentType,
    required this.hasVideo,
    required this.videoReady,
    required this.progress,
    this.estimatedMinutes,
  });

  final String id;
  final String title;
  final String contentType;
  final bool hasVideo;

  /// False mientras el worker transcodifica: la app muestra "procesando" en lugar de un
  /// reproductor que fallaría al pedir el playlist.
  final bool videoReady;
  final LessonProgress progress;
  final int? estimatedMinutes;

  factory PathLesson.fromJson(Map<String, dynamic> json) => PathLesson(
        id: json['id'] as String,
        title: json['title'] as String,
        contentType: json['content_type'] as String,
        hasVideo: json['has_video'] as bool,
        videoReady: json['video_ready'] as bool,
        estimatedMinutes: json['estimated_minutes'] as int?,
        progress: LessonProgress.fromJson(json['progress'] as Map<String, dynamic>),
      );
}

class PathModule {
  const PathModule({
    required this.id,
    required this.title,
    required this.locked,
    required this.completedLessons,
    required this.totalLessons,
    required this.lessons,
    this.description,
  });

  final String id;
  final String title;
  final String? description;

  /// El backend decide el bloqueo; la app solo lo pinta. La comprobación real se repite en el
  /// servidor al abrir la lección.
  final bool locked;
  final int completedLessons;
  final int totalLessons;
  final List<PathLesson> lessons;

  factory PathModule.fromJson(Map<String, dynamic> json) => PathModule(
        id: json['id'] as String,
        title: json['title'] as String,
        description: json['description'] as String?,
        locked: json['locked'] as bool,
        completedLessons: json['completed_lessons'] as int,
        totalLessons: json['total_lessons'] as int,
        lessons: (json['lessons'] as List)
            .map((item) => PathLesson.fromJson(item as Map<String, dynamic>))
            .toList(),
      );
}

class LearningPath {
  const LearningPath({
    required this.machineModelId,
    required this.machineName,
    required this.machineCode,
    required this.totalLessons,
    required this.completedLessons,
    required this.progressPercent,
    required this.modules,
  });

  final String machineModelId;
  final String machineName;
  final String machineCode;
  final int totalLessons;
  final int completedLessons;
  final double progressPercent;
  final List<PathModule> modules;

  factory LearningPath.fromJson(Map<String, dynamic> json) => LearningPath(
        machineModelId: json['machine_model_id'] as String,
        machineName: json['machine_name'] as String,
        machineCode: json['machine_code'] as String,
        totalLessons: json['total_lessons'] as int,
        completedLessons: json['completed_lessons'] as int,
        progressPercent: (json['progress_percent'] as num).toDouble(),
        modules: (json['modules'] as List)
            .map((item) => PathModule.fromJson(item as Map<String, dynamic>))
            .toList(),
      );
}

class LessonDetail {
  const LessonDetail({
    required this.id,
    required this.title,
    required this.contentType,
    required this.progress,
    this.body,
    this.durationSeconds,
    this.hlsMasterUrl,
    this.documentUrl,
    this.estimatedMinutes,
  });

  final String id;
  final String title;
  final String contentType;
  final String? body;
  final double? durationSeconds;

  /// Ruta relativa al API; hay que prefijar el host antes de dársela al reproductor.
  final String? hlsMasterUrl;
  final String? documentUrl;
  final int? estimatedMinutes;
  final LessonProgress progress;

  String? get absoluteHlsUrl =>
      hlsMasterUrl == null ? null : '${AppConfig.apiBaseUrl}$hlsMasterUrl';

  factory LessonDetail.fromJson(Map<String, dynamic> json) => LessonDetail(
        id: json['id'] as String,
        title: json['title'] as String,
        contentType: json['content_type'] as String,
        body: json['body'] as String?,
        durationSeconds: (json['duration_seconds'] as num?)?.toDouble(),
        hlsMasterUrl: json['hls_master_url'] as String?,
        documentUrl: json['document_url'] as String?,
        estimatedMinutes: json['estimated_minutes'] as int?,
        progress: LessonProgress.fromJson(json['progress'] as Map<String, dynamic>),
      );
}

/// Lección no accesible todavía porque falta completar el módulo anterior.
class LessonLockedException implements Exception {
  const LessonLockedException(this.message);
  final String message;
  @override
  String toString() => message;
}

class LmsRepository {
  LmsRepository({required this.client});

  final ApiClient client;

  Future<LearningPath> learningPath(String machineModelId) async {
    final response = await client.dio.get('/lms/machines/$machineModelId/path');
    if (response.statusCode != 200) {
      throw Exception('Could not load the training (${response.statusCode}).');
    }
    return LearningPath.fromJson(response.data as Map<String, dynamic>);
  }

  Future<LessonDetail> lesson(String lessonId) async {
    final response = await client.dio.get('/lms/lessons/$lessonId');
    if (response.statusCode == 403) {
      throw const LessonLockedException(
        'Complete the previous module to open this lesson.',
      );
    }
    if (response.statusCode != 200) {
      throw Exception('Could not load the lesson (${response.statusCode}).');
    }
    return LessonDetail.fromJson(response.data as Map<String, dynamic>);
  }

  /// Reporta la posición del reproductor.
  ///
  /// Solo se envía la posición: el porcentaje lo calcula el servidor contra la duración real del
  /// video. Si lo enviara el cliente, completar la capacitación sin verla sería un `PUT`.
  Future<LessonProgress?> reportProgress(String lessonId, double positionSeconds) async {
    final response = await client.dio.put(
      '/lms/lessons/$lessonId/progress',
      data: {'position_seconds': positionSeconds},
    );
    if (response.statusCode != 200) {
      return null;
    }
    return LessonProgress.fromJson(response.data as Map<String, dynamic>);
  }
}
