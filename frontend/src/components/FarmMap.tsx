import { useEffect } from 'react'
import { CircleMarker, MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import type { LatLngExpression } from 'leaflet'
import 'leaflet/dist/leaflet.css'

interface FarmMapProps {
  latitude: number
  longitude: number
  onChange: (latitude: number, longitude: number) => void
}

function ClickHandler({ onChange }: { onChange: FarmMapProps['onChange'] }) {
  useMapEvents({
    click(event) {
      onChange(
        Number(event.latlng.lat.toFixed(5)),
        Number(event.latlng.lng.toFixed(5)),
      )
    },
  })
  return null
}

function Recenter({ latitude, longitude }: { latitude: number; longitude: number }) {
  const map = useMap()
  useEffect(() => {
    map.setView([latitude, longitude], map.getZoom(), { animate: false })
  }, [latitude, longitude, map])
  return null
}

export default function FarmMap({ latitude, longitude, onChange }: FarmMapProps) {
  const center: LatLngExpression = [latitude, longitude]
  return (
    <div className="h-80 overflow-hidden rounded-xl border border-neutral-200">
      <MapContainer center={center} zoom={8} scrollWheelZoom className="h-full w-full">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <CircleMarker
          center={center}
          radius={9}
          pathOptions={{ color: '#4f46e5', fillColor: '#4f46e5', fillOpacity: 0.85 }}
        />
        <ClickHandler onChange={onChange} />
        <Recenter latitude={latitude} longitude={longitude} />
      </MapContainer>
    </div>
  )
}
