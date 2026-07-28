import '../../../core/network/api_client.dart';

/// Máquina resuelta a partir del QR escaneado.
class ResolvedMachine {
  const ResolvedMachine({
    required this.machineModelId,
    required this.code,
    required this.name,
    required this.specialty,
    this.description,
    required this.modulesCount,
  });

  final String machineModelId;
  final String code;
  final String name;
  final String specialty;
  final String? description;
  final int modulesCount;

  factory ResolvedMachine.fromJson(Map<String, dynamic> json) => ResolvedMachine(
        machineModelId: json['machine_model_id'] as String,
        code: json['code'] as String,
        name: json['name'] as String,
        specialty: json['specialty'] as String,
        description: json['description'] as String?,
        modulesCount: json['modules_count'] as int,
      );
}

/// Resultado del escaneo, con el motivo del fallo cuando no se resuelve.
sealed class ScanResult {
  const ScanResult();
}

class ScanSuccess extends ScanResult {
  const ScanSuccess(this.machine);
  final ResolvedMachine machine;
}

class ScanNotFound extends ScanResult {
  const ScanNotFound(this.message);
  final String message;
}

class ScanError extends ScanResult {
  const ScanError(this.message);
  final String message;
}

/// Entrada del catálogo de equipos.
///
/// Lleva el `qr_token` para poder abrir la capacitación **sin cámara**: en un emulador, o cuando
/// el adhesivo del equipo está deteriorado, esa es la única vía practicable.
class MachineSummary {
  const MachineSummary({
    required this.id,
    required this.code,
    required this.name,
    required this.specialty,
    required this.qrToken,
    this.manufacturer,
    this.description,
    this.lessonsCount = 0,
    this.completedLessons = 0,
    this.progressPercent = 0,
  });

  final String id;
  final String code;
  final String name;
  final String specialty;
  final String qrToken;
  final String? manufacturer;

  /// El backend ya la devolvía en `MachineRead`; simplemente no se estaba leyendo.
  final String? description;

  /// Progreso del usuario autenticado, agregado por el backend en dos consultas fijas. Pedirlo por
  /// máquina con `/lms/machines/{id}/path` sería un N+1 que crece con el catálogo.
  final int lessonsCount;
  final int completedLessons;
  final double progressPercent;

  bool get isStarted => completedLessons > 0;
  bool get isComplete => lessonsCount > 0 && completedLessons >= lessonsCount;

  factory MachineSummary.fromJson(Map<String, dynamic> json) => MachineSummary(
    id: json['id'] as String,
    code: json['code'] as String,
    name: json['name'] as String,
    specialty: json['specialty'] as String,
    qrToken: json['qr_token'] as String,
    manufacturer: json['manufacturer'] as String?,
    description: json['description'] as String?,
    // Opcionales con valor por defecto: un backend anterior a este cambio sigue funcionando, y
    // los tests existentes que construyen el objeto a mano no se rompen.
    lessonsCount: (json['lessons_count'] as num?)?.toInt() ?? 0,
    completedLessons: (json['completed_lessons'] as num?)?.toInt() ?? 0,
    progressPercent: (json['progress_percent'] as num?)?.toDouble() ?? 0,
  );
}

class MachineRepository {
  MachineRepository({required this.client});

  final ApiClient client;

  /// Catálogo de equipos publicados.
  Future<List<MachineSummary>> list() async {
    final response = await client.dio.get('/machines');
    if (response.statusCode != 200) {
      throw Exception('Could not load the catalogue (${response.statusCode}).');
    }
    return (response.data as List)
        .map((item) => MachineSummary.fromJson((item as Map).cast<String, dynamic>()))
        .toList();
  }

  /// Resuelve el token del QR.
  ///
  /// Es el único punto de la app que traduce un QR a una entidad de dominio. Si algún día el QR
  /// apunta a una unidad física en lugar de a un modelo de equipo, el cambio ocurre en el
  /// backend y aquí no se toca nada: la app sigue recibiendo un `machine_model_id`.
  Future<ScanResult> resolve(String qrToken) async {
    try {
      final response = await client.dio.get('/machines/resolve/$qrToken');
      if (response.statusCode == 200) {
        return ScanSuccess(
          ResolvedMachine.fromJson(response.data as Map<String, dynamic>),
        );
      }
      if (response.statusCode == 404) {
        return const ScanNotFound(
          'This QR code does not match any equipment with published training.',
        );
      }
      return ScanError('The server responded ${response.statusCode}.');
    } catch (error) {
      return const ScanError('Could not reach the server. Check your connection.');
    }
  }
}
