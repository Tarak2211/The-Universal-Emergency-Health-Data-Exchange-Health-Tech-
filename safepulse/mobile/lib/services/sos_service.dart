import 'dart:async';
import 'package:dio/dio.dart';
import '../config.dart';

class SOSService {
  final Dio _dio;
  String? _activeSosId;
  Timer? _countdownTimer;

  SOSService(this._dio);

  Future<String?> triggerSOS({
    required double latitude,
    required double longitude,
    required double gForcePeak,
    required String severity,
  }) async {
    try {
      final resp = await _dio.post('${AppConfig.apiBase}/sos/trigger', data: {
        'latitude': latitude,
        'longitude': longitude,
        'g_force_peak': gForcePeak,
        'severity': severity,
      });
      _activeSosId = resp.data['sos_id'];
      return _activeSosId;
    } catch (e) {
      return null;
    }
  }

  Future<bool> cancelSOS() async {
    if (_activeSosId == null) return false;
    try {
      await _dio.post('${AppConfig.apiBase}/sos/$_activeSosId/cancel');
      _activeSosId = null;
      return true;
    } catch (e) {
      return false;
    }
  }

  Future<Map<String, dynamic>?> getMedicalId() async {
    try {
      final resp = await _dio.get('${AppConfig.apiBase}/sos/medical-id');
      return resp.data;
    } catch (e) {
      return null;
    }
  }
}
