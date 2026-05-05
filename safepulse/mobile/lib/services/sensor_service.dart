import 'dart:math';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:geolocator/geolocator.dart';
import 'sos_service.dart';

class SensorService {
  static const double HIGH_IMPACT_G = 4.0;
  static const double SEVERE_G = 8.0;
  static const double STILLNESS_THRESHOLD = 1.2;
  static const double GRAVITY = 9.81;

  final SOSService _sosService;
  final List<Map<String, dynamic>> _recentReadings = [];
  bool _sosTriggered = false;

  SensorService(this._sosService);

  void startListening() {
    accelerometerEvents.listen((AccelerometerEvent event) {
      final g = _calcG(event.x, event.y, event.z);
      _recentReadings.add({
        'g': g,
        'ax': event.x,
        'ay': event.y,
        'az': event.z,
        'time': DateTime.now(),
      });

      // Keep only last 5 seconds of readings
      final cutoff = DateTime.now().subtract(const Duration(seconds: 5));
      _recentReadings.removeWhere((r) => (r['time'] as DateTime).isBefore(cutoff));

      if (g >= HIGH_IMPACT_G && !_sosTriggered) {
        _checkForAccident(g);
      }
    });
  }

  double _calcG(double ax, double ay, double az) {
    return sqrt(ax * ax + ay * ay + az * az) / GRAVITY;
  }

  Future<void> _checkForAccident(double peakG) async {
    // Wait 3 seconds to observe post-impact stillness
    await Future.delayed(const Duration(seconds: 3));

    final now = DateTime.now();
    final postImpact = _recentReadings
        .where((r) => (r['time'] as DateTime).isAfter(now.subtract(const Duration(seconds: 3))))
        .toList();

    if (postImpact.isEmpty) return;

    final avgG = postImpact.map((r) => r['g'] as double).reduce((a, b) => a + b) / postImpact.length;

    // False alarm: phone was dropped and picked up
    if (avgG > STILLNESS_THRESHOLD) return;

    _sosTriggered = true;
    final position = await Geolocator.getCurrentPosition();
    final severity = peakG >= SEVERE_G ? 'severe' : 'moderate';

    await _sosService.triggerSOS(
      latitude: position.latitude,
      longitude: position.longitude,
      gForcePeak: peakG,
      severity: severity,
    );
  }

  void reset() => _sosTriggered = false;
}
