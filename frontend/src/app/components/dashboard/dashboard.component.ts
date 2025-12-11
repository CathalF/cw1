import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { Competition, Match, Paginated, Team } from '../../models';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.css']
})
export class DashboardComponent implements OnInit {
  competitions: Competition[] = [];
  teams: Team[] = [];
  matches: Match[] = [];
  loading = true;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.refresh();
  }

  private refresh(): void {
    this.loading = true;
    this.api.listCompetitions().subscribe((res: Paginated<Competition>) => {
      this.competitions = res.items.slice(0, 4);
    });
    this.api.listTeams().subscribe((res: Paginated<Team>) => {
      this.teams = res.items.slice(0, 5);
    });
    this.api.listMatches().subscribe((res: Paginated<Match>) => {
      this.matches = res.items.slice(0, 5);
      this.loading = false;
    });
  }
}
