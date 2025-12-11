import { Routes } from '@angular/router';
import { DashboardComponent } from './components/dashboard/dashboard.component';
import { LoginComponent } from './components/login/login.component';
import { RegisterComponent } from './components/register/register.component';
import { CompetitionsComponent } from './components/competitions/competitions.component';
import { TeamsComponent } from './components/teams/teams.component';
import { MatchesComponent } from './components/matches/matches.component';
import { PlayersComponent } from './components/players/players.component';
import { NotesComponent } from './components/notes/notes.component';
import { AnalyticsComponent } from './components/analytics/analytics.component';

export const routes: Routes = [
  { path: '', component: DashboardComponent },
  { path: 'login', component: LoginComponent },
  { path: 'register', component: RegisterComponent },
  { path: 'competitions', component: CompetitionsComponent },
  { path: 'teams', component: TeamsComponent },
  { path: 'matches', component: MatchesComponent },
  { path: 'players', component: PlayersComponent },
  { path: 'notes/:matchId', component: NotesComponent },
  { path: 'analytics', component: AnalyticsComponent },
  { path: '**', redirectTo: '' }
];
