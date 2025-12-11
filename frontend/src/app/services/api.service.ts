import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../environments/environment';
import { Competition, Paginated, Team, Player, Match, Note, FormResponse } from '../models';
import { Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private base = environment.apiBaseUrl;

  constructor(private http: HttpClient) {}

  listCompetitions(): Observable<Paginated<Competition>> {
    return this.http.get<Paginated<Competition>>(`${this.base}/competitions`);
  }

  listTeams(filter?: { name?: string; country?: string }): Observable<Paginated<Team>> {
    let params = new HttpParams();
    if (filter?.name) params = params.set('name', filter.name);
    if (filter?.country) params = params.set('country', filter.country);
    return this.http.get<Paginated<Team>>(`${this.base}/teams`, { params });
  }

  listPlayers(filter?: { team_id?: string; position?: string }): Observable<Paginated<Player>> {
    let params = new HttpParams();
    if (filter?.team_id) params = params.set('team_id', filter.team_id);
    if (filter?.position) params = params.set('position', filter.position);
    return this.http.get<Paginated<Player>>(`${this.base}/players`, { params });
  }

  listMatches(filter?: {
    competition_id?: string;
    season_id?: string;
    team_id?: string;
    status?: string;
  }): Observable<Paginated<Match>> {
    let params = new HttpParams();
    if (filter?.competition_id) params = params.set('competition_id', filter.competition_id);
    if (filter?.season_id) params = params.set('season_id', filter.season_id);
    if (filter?.team_id) params = params.set('team_id', filter.team_id);
    if (filter?.status) params = params.set('status', filter.status);
    return this.http.get<Paginated<Match>>(`${this.base}/matches`, { params });
  }

  getMatch(id: string): Observable<Match> {
    return this.http.get<Match>(`${this.base}/matches/${id}`);
  }

  listNotes(matchId: string): Observable<Note[]> {
    const params = new HttpParams().set('match_id', matchId);
    return this.http.get<Note[]>(`${this.base}/notes`, { params });
  }

  createNote(matchId: string, note: string): Observable<Note> {
    return this.http.post<Note>(`${this.base}/notes`, { match_id: matchId, note });
  }

  deleteNote(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/notes/${id}`);
  }

  fetchFormAnalytics(): Observable<FormResponse> {
    return this.http.get<FormResponse>(`${this.base}/analytics/form`);
  }
}
