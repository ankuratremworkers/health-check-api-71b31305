import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { useEffect, useState } from 'react';

import { api } from './services/api';
import { resolve } from './services/dataSource';
import { mockData } from './services/mockData';

// Root component. All styling goes in `sx` — MUI v6 dropped the shorthand props.
export function App() {
  const [status, setStatus] = useState('…');

  useEffect(() => {
    resolve(
      () => api.get<{ status: string }>('/api/health').then((r) => r.data),
      mockData.endpoints['GET /api/health'][0],
    )
      .then((r) => setStatus(r.status))
      .catch(() => setStatus('unreachable'));
  }, []);

  return (
    <Box sx={{ p: 4 }}>
      <Typography variant="h4">Health Service</Typography>
      <Typography variant="body2" sx={{ mt: 1, color: 'text.secondary' }}>
        backend: {status}
      </Typography>
    </Box>
  );
}
