import { useEffect, useState } from 'react';

export function useMobile() {
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 1190px)').matches);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 1190px)');
    const update = () => setMobile(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return mobile;
}
