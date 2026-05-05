import { useState } from 'react';
import api from '../api/client';

export default function PaymentPage() {
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState('');

  const initiatePayment = async () => {
    try {
      const { data } = await api.post('/payments/create-order', {
        amount_paise: Math.round(parseFloat(amount) * 100),
        description,
      });

      const options = {
        key: process.env.REACT_APP_RAZORPAY_KEY,
        amount: data.amount,
        currency: 'INR',
        order_id: data.order_id,
        name: 'SafePulse Health',
        description,
        handler: async (response) => {
          await api.post('/payments/verify', {
            order_id: data.order_id,
            payment_id: response.razorpay_payment_id,
            signature: response.razorpay_signature,
          });
          setStatus('Payment successful.');
        },
        prefill: { name: '', email: '', contact: '' },
        theme: { color: '#1d4ed8' },
      };

      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch {
      setStatus('Payment initiation failed.');
    }
  };

  return (
    <div className="p-8 max-w-md mx-auto">
      <h1 className="text-2xl font-bold mb-6">Pay Hospital / Pharmacy Bill</h1>
      <div className="bg-white rounded-lg shadow p-6">
        <input className="border rounded px-3 py-2 w-full mb-3" placeholder="Amount (₹)" type="number" value={amount} onChange={e => setAmount(e.target.value)} />
        <input className="border rounded px-3 py-2 w-full mb-4" placeholder="Description (e.g. Hospital Bill)" value={description} onChange={e => setDescription(e.target.value)} />
        <button onClick={initiatePayment} className="bg-blue-600 text-white w-full py-2 rounded hover:bg-blue-700">Pay via UPI</button>
        {status && <p className="mt-3 text-sm text-green-700">{status}</p>}
      </div>
    </div>
  );
}
