import type { Metric } from '../types/domain';
const numberFormat=new Intl.NumberFormat('en-US',{maximumFractionDigits:2});
export function formatUnit(unit:string):string {return ({mwh:'MWh',mw:'MW',kg_CO2e_per_mwh:'kg CO₂e/MWh',tonnes_CO2e:'t CO₂e',m3_consumed:'m³ consumed',m3_withdrawn:'m³ withdrawn',liters_consumption_per_IT_kwh:'L/IT kWh',score_0_to_5:'index (0–5)',score_0_to_100:'score (0–100)',frac:'fraction (0–1)',degC:'°C',degrees_C:'°C'} as Record<string,string>)[unit]??unit;}
export function formatScore(value:number|null|undefined):string {return typeof value==='number'&&Number.isFinite(value)?value.toFixed(1):'Unknown';}
export function formatMetric(metric:Metric):string {if(metric.value===null||metric.status==='unknown')return 'Unknown';const value=typeof metric.value==='number'?numberFormat.format(metric.value):metric.value;return metric.unit?`${value} ${formatUnit(metric.unit)}`:value;}
export function safeSourceUrl(value:string|null|undefined):string|null {if(!value)return null;try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?url.href:null;}catch{return null;}}
export function safeExportUrl(value:string):string|null {if(value.startsWith('/api/exports/')&&!value.includes('\\')&&!value.includes('..'))return `${(import.meta.env.VITE_API_BASE_URL??'').replace(/\/$/,'')}${value}`;return safeSourceUrl(value);}
