import { useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

maplibregl.setWorkerUrl(workerUrl);

const BASEMAP_STYLE = 'https://tiles.openfreemap.org/styles/positron';
export default function HeatMap({
  grid,
  center,
  zoom,
  placements,
  selectedCell,
  highlightQuintileV,
  onCellClick,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const loadedRef = useRef(false);
  const clickHandlerRef = useRef(onCellClick);
  const [hovered, setHovered] = useState(null);

  useEffect(() => {
    clickHandlerRef.current = onCellClick;
  }, [onCellClick]);

  // Enrich GeoJSON with live placement & selection state
  const enrichedGrid = useMemo(() => {
    if (!grid) return { type: 'FeatureCollection', features: [] };
    const counts = {};
    for (const p of placements) {
      counts[p.h3_index] = (counts[p.h3_index] || 0) + p.units;
    }
    return {
      ...grid,
      features: grid.features.map((f) => {
        const id = f.properties.h3_index;
        return {
          ...f,
          properties: {
            ...f.properties,
            placed_units: counts[id] || 0,
            is_selected: id === selectedCell ? 1 : 0,
          },
        };
      }),
    };
  }, [grid, placements, selectedCell]);

  const latestGridRef = useRef(enrichedGrid);
  latestGridRef.current = enrichedGrid;
  // Initialize MapLibre once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP_STYLE,
      center: center || [29.9245, 31.2058],
      zoom: zoom || 12.2,
    });
    map.addControl(new maplibregl.NavigationControl(), 'top-right');

    map.on('load', () => {
      loadedRef.current = true;
      map.addSource('h3-grid', {
        type: 'geojson',
        data: latestGridRef.current,
      });

      // HVI Choropleth (NA / water cells rendered muted gray)
      // HVI Choropleth (hide open-water cells; keep missing-data land cells in gray)
      map.addLayer({
        id: 'h3-fill',
        type: 'fill',
        source: 'h3-grid',
        filter: ['!=', ['get', 'data_status'], 'water_masked'],
        paint: {
          'fill-color': [
            'case',
            ['==', ['get', 'baseline_hvi'], null],
            '#cbd5e1',
            [
              'interpolate',
              ['linear'],
              ['get', 'baseline_hvi'],
              20, '#fef3c7',
              45, '#fbbf24',
              65, '#f97316',
              85, '#dc2626',
            ],
          ],
          'fill-opacity': [
            'case',
            ['==', ['get', 'baseline_hvi'], null],
            0.35,
            0.55,
          ],
        },
      });

      // Base hex borders (land cells only)
      map.addLayer({
        id: 'h3-outline',
        type: 'line',
        source: 'h3-grid',
        filter: ['!=', ['get', 'data_status'], 'water_masked'],
        paint: {
          'line-color': '#475569',
          'line-width': 0.5,
          'line-opacity': 0.4,
        },
      });

      // Subtle emerald fill tint on treated cells so selection never hides placement
      map.addLayer({
        id: 'h3-placed-fill',
        type: 'fill',
        source: 'h3-grid',
        filter: ['>', ['get', 'placed_units'], 0],
        paint: {
          'fill-color': '#10b981',
          'fill-opacity': 0.35,
        },
      });

      // Top HVI Quintile V highlight border
      map.addLayer({
        id: 'h3-quintile-v',
        type: 'line',
        source: 'h3-grid',
        filter: ['==', ['get', 'in_top_hvi_quintile_v'], true],
        paint: {
          'line-color': '#7f1d1d',
          'line-width': 1.8,
          'line-dasharray': [2, 1.5],
        },
      });

      // Active placed interventions border
      map.addLayer({
        id: 'h3-placed',
        type: 'line',
        source: 'h3-grid',
        filter: ['>', ['get', 'placed_units'], 0],
        paint: {
          'line-color': '#059669',
          'line-width': 3.2,
        },
      });

      // Selected cell highlight
      map.addLayer({
        id: 'h3-selected',
        type: 'line',
        source: 'h3-grid',
        filter: ['==', ['get', 'is_selected'], 1],
        paint: {
          'line-color': '#0f172a',
          'line-width': 2.2,
        },
      });

      map.on('mousemove', 'h3-fill', (e) => {
        map.getCanvas().style.cursor = 'pointer';
        const props = e.features?.[0]?.properties;
        if (props) setHovered(props);
      });

      map.on('mouseleave', 'h3-fill', () => {
        map.getCanvas().style.cursor = '';
        setHovered(null);
      });

      map.on('click', 'h3-fill', (e) => {
        const props = e.features?.[0]?.properties;
        if (props && clickHandlerRef.current) {
          clickHandlerRef.current(props);
        }
      });

      // Push initial grid if already loaded before map 'load' fired
      const src = map.getSource('h3-grid');
      
      
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      loadedRef.current = false;
    };
  }, []);

  // Update GeoJSON data whenever grid or placements change
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    const src = map.getSource('h3-grid');
    if (src) src.setData(enrichedGrid);
  }, [enrichedGrid]);

  // Toggle Quintile V layer visibility
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    if (map.getLayer('h3-quintile-v')) {
      map.setLayoutProperty(
        'h3-quintile-v',
        'visibility',
        highlightQuintileV ? 'visible' : 'none'
      );
    }
  }, [highlightQuintileV]);

  // Fly to city when center changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !center) return;
    map.flyTo({ center, zoom: zoom || 12.2, duration: 900 });
  }, [center?.[0], center?.[1], zoom]);

  return (
    <div className="map-wrapper">
      <div ref={containerRef} className="map-canvas" />

      <div className="map-legend">
        <div className="legend-title">AR4 Heat Priority Index (HVI)</div>
        <div className="legend-scale">
          <span className="swatch" style={{ background: '#fef3c7' }} /> 20
          <span className="swatch" style={{ background: '#fbbf24' }} /> 45
          <span className="swatch" style={{ background: '#f97316' }} /> 65
          <span className="swatch" style={{ background: '#dc2626' }} /> 85+
          <span className="swatch" style={{ background: '#cbd5e1' }} /> NA / Water
        </div>
        <div className="legend-notes">
          <span><i className="line-chip green" /> Treated Cell</span>
          <span><i className="line-chip red-dash" /> Top HVI Quintile V</span>
        </div>
      </div>

      {hovered && (
        <div className="map-tooltip">
          <div className="tt-id">{hovered.h3_index}</div>
          <div>HVI: <strong>{hovered.baseline_hvi ?? 'NA (Unscored)'}</strong> {hovered.in_top_hvi_quintile_v ? '(Top 20% V)' : ''}</div>
          <div>Summer LST: <strong>{hovered.lst_summer_c != null ? `${hovered.lst_summer_c} °C` : 'Masked'}</strong></div>
          <div>Pop: <strong>{Number(hovered.population_count || 0).toLocaleString()}</strong> | Transit Stops: <strong>{hovered.transit_stops}</strong></div>
          <div>Status: <span className="mono">{hovered.data_status}</span> | Placed Units: <strong>{hovered.placed_units}</strong></div>
        </div>
      )}
    </div>
  );
}