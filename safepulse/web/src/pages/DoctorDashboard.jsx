import { useState } from 'react';
import api from '../api/client';

export default function DoctorDashboard() {
  const [abhaId, setAbhaId] = useState('');
  const [records, setRecords] = useState(null);
  const [prescription, setPrescription] = useState({ diagnosis: '', medicines: '', notes: '' });
  const [patientId, setPatientId] = useState('');
  const [message, setMessage] = useState('');

  const fetchRecords = async () => {
    try {
      const r = await api.get(`/medical/abha/${abhaId}/records`);
      setRecords(r.data);
    } catch {
      setMessage('Failed to fetch records. Check ABHA ID.');
    }
  };

  const issuePrescription = async () => {
    try {
      await api.post('/medical/prescription', {
        patient_id: patientId,
        content: {
          diagnosis: prescription.diagnosis,
          medicines: prescription.medicines.split(',').map(m => m.trim()),
          notes: prescription.notes,
        }
      });
      setMessage('Prescription issued successfully.');
    } catch {
      setMessage('Failed to issue prescription.');
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Doctor Dashboard</h1>

      <section className="mb-8 bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">Fetch Patient Records via ABHA ID</h2>
        <div className="flex gap-3">
          <input className="border rounded px-3 py-2 flex-1" placeholder="Enter ABHA ID" value={abhaId} onChange={e => setAbhaId(e.target.value)} />
          <button onClick={fetchRecords} className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Fetch</button>
        </div>
        {records && (
          <pre className="mt-4 bg-gray-50 p-4 rounded text-sm overflow-auto max-h-64">
            {JSON.stringify(records, null, 2)}
          </pre>
        )}
      </section>

      <section className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">Issue Digital Prescription</h2>
        <input className="border rounded px-3 py-2 w-full mb-3" placeholder="Patient ID (UUID)" value={patientId} onChange={e => setPatientId(e.target.value)} />
        <input className="border rounded px-3 py-2 w-full mb-3" placeholder="Diagnosis" value={prescription.diagnosis} onChange={e => setPrescription(p => ({...p, diagnosis: e.target.value}))} />
        <input className="border rounded px-3 py-2 w-full mb-3" placeholder="Medicines (comma separated)" value={prescription.medicines} onChange={e => setPrescription(p => ({...p, medicines: e.target.value}))} />
        <textarea className="border rounded px-3 py-2 w-full mb-3" placeholder="Notes" rows={3} value={prescription.notes} onChange={e => setPrescription(p => ({...p, notes: e.target.value}))} />
        <button onClick={issuePrescription} className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700">Issue Prescription</button>
        {message && <p className="mt-3 text-sm text-blue-700">{message}</p>}
      </section>
    </div>
  );
}
