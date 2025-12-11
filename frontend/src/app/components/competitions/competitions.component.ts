import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { ApiService } from '../../services/api.service';
import { Competition, Paginated } from '../../models';

@Component({
  selector: 'app-competitions',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './competitions.component.html',
  styleUrls: ['./competitions.component.css']
})
export class CompetitionsComponent implements OnInit {
  competitions: Competition[] = [];
  loading = false;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading = true;
    this.api.listCompetitions().subscribe((res: Paginated<Competition>) => {
      this.competitions = res.items;
      this.loading = false;
    });
  }
}
