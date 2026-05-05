import { useEffect, useState } from 'react';
import api from '../api/client';

export default function AdminDashboard() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/analytics/hotspots')
      .then(r => setReport(r.data))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-center">Loading analytics...</div>;

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-6">SafePulse Admin Dashboard</h1>

      <div className="grid grid-cols-3 gap-4 mb-8">
        <StatCard label="Total Incidents (90d)" value={report?.total_incidents ?? 0} />
        <StatCard label="Avg Response Time" value={`${report?.avg_response_minutes ?? 0} min`} />
        <StatCard label="Top Danger Zones" value={report?.top_hotspots?.length ?? 0} />
      </div>

      {report?.report_url && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold mb-3">Accident Hotspot Map</h2>
          <img src={`${process.env.REACT_APP_API_URL}${report.report_url}`} alt="Hotspot heatmap" className="rounded-lg shadow" />
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold mb-3">Top 5 Danger Zones</h2>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-100">
              <th className="p-2 text-left">Lat</th>
              <th className="p-2 text-left">Lon</th>
              <th className="p-2 text-left">Incidents</th>
              <th className="p-2 text-left">Avg G-Force</th>
              <th className="p-2 text-left">Avg Response (min)</th>
            </tr>
          </thead>
          <tbody>
            {(report?.top_hotspots ?? []).map((z, i) => (
              <tr key={i} className="border-t">
                <td className="p-2">{z.lat_bin}</td>
                <td className="p-2">{z.lon_bin}</td>
                <td className="p-2 font-bold text-red-600">{z.incident_count}</td>
                <td className="p-2">{z.avg_g_force?.toFixed(2)}</td>
                <td className="p-2">{z.avg_response_min?.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="bg-white rounded-lg shadow p-4 border-l-4 border-blue-500">
      <p className="text-gray-500 text-sm">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
    </div>
  );
}
