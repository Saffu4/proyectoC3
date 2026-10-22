// Tipos del dominio — espejo de la API del dispositivo
export type Side = "granted" | "denied";
export type PersonStatus = "active" | "suspended" | "revoked";

export interface Person {
  id: string;
  full_name: string;
  document_id: string | null;
  status: PersonStatus;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PersonDetail extends Person {
  roles: string[];
  face_profile: { id: string; model_label: number; enabled: number; created_at: string } | null;
  face_images_count?: number;
  face_images?: string[];
}

export interface Role {
  id: number;
  name: string;
  description: string | null;
  permissions: string[];
}

export interface AccessEvent {
  event_id: string;
  person_id: string | null;
  full_name: string | null;
  result: Side;
  reason: string;
  category: string | null;
  timestamp: string;
  confidence: number | null;
}

export interface DeviceStatus {
  device_id: string;
  camera: { available: boolean; error: string | null };
  model: { trained: boolean; threshold: number; faces_trained: number };
  sync: { enabled: boolean; last_policy_sync: string | null; age_hours: number | null; stale: boolean };
  events: { total: number; granted: number; denied: number; unsynced: number };
  pending_events: number;
}

export interface AuditEntry {
  action: string;
  actor: string;
  detail: string | null;
  timestamp: string;
}
