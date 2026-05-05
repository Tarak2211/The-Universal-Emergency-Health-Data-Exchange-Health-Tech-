import 'dart:async';
import 'package:flutter/material.dart';
import '../services/sos_service.dart';

class SOSCountdownScreen extends StatefulWidget {
  final SOSService sosService;
  const SOSCountdownScreen({super.key, required this.sosService});

  @override
  State<SOSCountdownScreen> createState() => _SOSCountdownScreenState();
}

class _SOSCountdownScreenState extends State<SOSCountdownScreen> {
  int _seconds = 30;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (_seconds <= 0) {
        t.cancel();
        Navigator.of(context).pop();
      } else {
        setState(() => _seconds--);
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _cancel() async {
    _timer?.cancel();
    await widget.sosService.cancelSOS();
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.red.shade900,
      body: SafeArea(
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.warning_amber_rounded, color: Colors.white, size: 80),
              const SizedBox(height: 24),
              const Text('ACCIDENT DETECTED', style: TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold)),
              const SizedBox(height: 16),
              Text('Calling emergency services in', style: TextStyle(color: Colors.white70, fontSize: 16)),
              const SizedBox(height: 16),
              Text('$_seconds', style: const TextStyle(color: Colors.white, fontSize: 80, fontWeight: FontWeight.bold)),
              const SizedBox(height: 40),
              ElevatedButton(
                onPressed: _cancel,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: Colors.red.shade900,
                  padding: const EdgeInsets.symmetric(horizontal: 48, vertical: 16),
                ),
                child: const Text("I'M OKAY — CANCEL SOS", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
