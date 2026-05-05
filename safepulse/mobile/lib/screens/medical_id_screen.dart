import 'package:flutter/material.dart';
import '../services/sos_service.dart';

class MedicalIDScreen extends StatefulWidget {
  final SOSService sosService;
  const MedicalIDScreen({super.key, required this.sosService});

  @override
  State<MedicalIDScreen> createState() => _MedicalIDScreenState();
}

class _MedicalIDScreenState extends State<MedicalIDScreen> {
  Map<String, dynamic>? _profile;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final data = await widget.sosService.getMedicalId();
    setState(() { _profile = data; _loading = false; });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    if (_profile == null) return const Scaffold(body: Center(child: Text('No medical profile found')));

    return Scaffold(
      backgroundColor: Colors.blue.shade900,
      appBar: AppBar(backgroundColor: Colors.blue.shade900, title: const Text('Medical ID', style: TextStyle(color: Colors.white))),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _row(Icons.person, 'Name', _profile!['name']),
            _row(Icons.bloodtype, 'Blood Type', _profile!['blood_type'] ?? 'Unknown'),
            _row(Icons.warning, 'Allergies', (_profile!['allergies'] as List?)?.join(', ') ?? 'None'),
            _row(Icons.medical_services, 'Conditions', (_profile!['conditions'] as List?)?.join(', ') ?? 'None'),
            _row(Icons.medication, 'Medications', (_profile!['medications'] as List?)?.join(', ') ?? 'None'),
            const Divider(color: Colors.white38, height: 32),
            const Text('Emergency Contacts', style: TextStyle(color: Colors.white70, fontSize: 14)),
            ...(_profile!['emergency_contacts'] as List? ?? []).map((c) =>
              ListTile(
                leading: const Icon(Icons.phone, color: Colors.greenAccent),
                title: Text('${c['name']} (${c['relation']})', style: const TextStyle(color: Colors.white)),
                subtitle: Text(c['phone'], style: const TextStyle(color: Colors.white70)),
              )
            ),
          ],
        ),
      ),
    );
  }

  Widget _row(IconData icon, String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: Row(children: [
      Icon(icon, color: Colors.white70, size: 20),
      const SizedBox(width: 12),
      Text('$label: ', style: const TextStyle(color: Colors.white70)),
      Expanded(child: Text(value, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold))),
    ]),
  );
}
