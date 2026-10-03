import React from 'react';
import ReactDOM from 'react-dom/client';
import {setWorkerUrl} from 'maplibre-gl';
import mapWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import App from './App';
import './styles.css';
// Vite must bundle the v6 ESM worker and its shared imports as a worker entry.
setWorkerUrl(mapWorkerUrl);
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
