export interface User {
  _id: string;
  email: string;
  role: 'user' | 'admin';
}

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface Competition {
  id: string;
  name: string;
  country?: string;
  code?: string;
}

export interface Season {
  id: string;
  name: string;
  year?: number;
  competition_id: string;
}

export interface Team {
  id: string;
  name: string;
  country?: string;
  code?: string;
}

export interface Match {
  id: string;
  competition_id: string;
  season_id: string;
  home_team_id: string;
  away_team_id: string;
  home_score?: number;
  away_score?: number;
  date?: string;
  status?: string;
}

export interface Player {
  id: string;
  name: string;
  position?: string;
  team_id?: string;
}

export interface Note {
  id: string;
  match_id: string;
  note: string;
  created_by: { user_id: string; username?: string; role?: string };
  created_at?: string;
  edited_at?: string | null;
}

export interface FormRow {
  team: string;
  n: number;
  form: string[];
  form_str: string;
}

export interface FormResponse {
  filters: Record<string, unknown>;
  data: FormRow[];
}
