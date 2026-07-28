/// Formateo de duraciones, porcentajes y fechas.
///
/// Sin `intl`: el único uso sería el nombre del mes y el formato de duración, y la interfaz es solo
/// en inglés (D-039). Veinte líneas propias frente a una dependencia con su propia inicialización y
/// sus ficheros de locale.
library;

const List<String> _months = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/// Segundos a `m:ss`, o `h:mm:ss` si pasa de la hora. Para el reproductor y para "reanudar en".
String durationLabel(num? seconds) {
  if (seconds == null || seconds < 0) {
    return '--:--';
  }
  final total = seconds.round();
  final hours = total ~/ 3600;
  final minutes = (total % 3600) ~/ 60;
  final secs = total % 60;
  final paddedSecs = secs.toString().padLeft(2, '0');
  if (hours > 0) {
    return '$hours:${minutes.toString().padLeft(2, '0')}:$paddedSecs';
  }
  return '$minutes:$paddedSecs';
}

/// Minutos estimados de una lección.
String minutesLabel(int? minutes) {
  if (minutes == null || minutes <= 0) {
    return '';
  }
  if (minutes < 60) {
    return '$minutes min';
  }
  final hours = minutes ~/ 60;
  final rest = minutes % 60;
  return rest == 0 ? '$hours h' : '$hours h $rest min';
}

/// Suma de minutos de una ruta completa.
String totalMinutesLabel(int minutes) => minutes <= 0 ? '' : minutesLabel(minutes);

/// Fecha ISO del backend a `26 Jul`. Si es de otro año, añade el año.
///
/// Se parsea a local a propósito: "completada el 26 de julio" es un dato que el usuario compara con
/// su propio calendario, no con UTC.
String completedAtLabel(String? iso) {
  if (iso == null || iso.isEmpty) {
    return '';
  }
  final parsed = DateTime.tryParse(iso)?.toLocal();
  if (parsed == null) {
    return '';
  }
  final month = _months[parsed.month - 1];
  if (parsed.year != DateTime.now().year) {
    return '${parsed.day} $month ${parsed.year}';
  }
  return '${parsed.day} $month';
}

/// Porcentaje sin decimales. Redondea hacia abajo por debajo del 100 para no anunciar "100%" en
/// algo que no está terminado — la diferencia importa cuando desbloquea el módulo siguiente.
String percentLabel(double? value) {
  if (value == null) {
    return '';
  }
  if (value >= 100) {
    return '100%';
  }
  return '${value.floor()}%';
}
